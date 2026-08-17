"""The traffic controller module.

This module implements the traffic controller for signalgroup based
control


Design principles:
1)  Each group connected to this unit is independent in operations
2)  Operation is not based on "phases" as such but merely phasering that
    gives preference order of next groups to start
3) The "preference" order is scanned based on requests, finding the next
    main phase with a request
4)  Controller simply gives permissions to start, everything else
    (e.g. intergreens, end requests) are handled by the groups

"""
# Copyright 2022 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

import json
from typing import Any

import pandas as pd

from .detector import Detector, Ext_Extender, ExtDetector, GrpDetector, e3Detector
from .extender import Extender, e3Extender
from .phase import SimplePhase
from .signal_controller import ControllerStatus, SignalController
from .signal_group import (
    SignalGroup,
    value_is_number,  # Should be in utils unit or something
)
from .timer import Timer


class PhaseRingController(SignalController):
    """Signal group based signal controller.

    This is a controller with flexible 'phaseless' operation
    The phase ring defines only a round robin preference for the
    groups to be started. Main tool for operation is the conflict matrix
    and independend operation of groups
    """

    def __init__(self, controller_id: str, options: dict[str, Any], timer: Timer):
        self.name = controller_id
        self.timer = timer
        self._options = options

        self.print_status: bool = bool(options.get("print_status", False))

        self.prev_status_string: str = "start"
        self.cur_status_string: str = "start"
        self.last_print_step: int = 0

        phase_ring = tuple(tuple(row) for row in options["phases"])

        intergreens = tuple(tuple(row) for row in options["intergreens"])

        self.group_ids: list[str] = options["group_list"]
        if len(phase_ring[0]) != len(self.group_ids):
            raise ValueError(
                f"Number of groups in phases doesn't match number of groups in group "
                f"list: Want {len(phase_ring[0])} Got {len(self.group_ids)}",
            )

        groups = []
        for contr_idx, group_id in enumerate(self.group_ids):
            group_options = options["signal_groups"][group_id]
            new_group = SignalGroup(
                self.timer,
                group_id,
                group_options,
                controller_index=contr_idx,
            )
            groups.append(new_group)

        self.groups: tuple[SignalGroup, ...] = tuple(groups)

        self.set_conflict_groups(
            intergreens,
        )

        # By default sumo ouptuts are the same as group list
        # i.e. for each group there is one output and the order
        # is the same as group order. This can be overridden with
        # function set_sumo_outputs
        self.sumo_outputs = self.groups

        # setup manin phases
        self.set_phase_ring(phase_ring)

        # We assign the detectors: extensiton detectors
        # ext_dets are later assigned to extenders
        # Requests are handled in this class
        self.req_dets = []
        self.ext_dets = []
        self.ext_groups = []
        self.extenders = []
        self.e3detectors = []
        self.e3extenders = []

        det_cnf = options["detectors"]

        for det in det_cnf:
            if det_cnf[det]["type"] == "request":
                new_det = Detector(self.timer, det, det_cnf[det])
                new_det.set_request_groups(self.groups)  # Into init?
                self.req_dets.append(new_det)  # Note: not used at the moment

            if det_cnf[det]["type"] == "extender":
                new_det = ExtDetector(self.timer, det, det_cnf[det])
                self.ext_dets.append(new_det)  # these are for detector extenders

            if det_cnf[det]["type"] == "ext_extender":
                new_det = Ext_Extender(self.timer, det, det_cnf[det])
                self.ext_dets.append(new_det)  # these are for detector extenders

            if det_cnf[det]["type"] == "groupext":
                new_det = GrpDetector(self.timer, det, det_cnf[det])
                new_det.extgroup = self.get_signal_group_object(new_det.extgroup_name)
                self.ext_groups.append(new_det)  # these are for group extenders

            if det_cnf[det]["type"] == "e3detector":
                new_det = e3Detector(
                    self.timer,
                    det,
                    det_cnf[det],
                )
                self.e3detectors.append(new_det)

            new_det.owngroup_obj = self.get_signal_group_object(new_det.owngroup_name)

        # DBIK240802 Only create an extender for a signal group, if there are extending detectors of its own
        ext_params = {}

        for group in self.groups:
            dets = []
            e3dets = []
            for det in self.ext_dets:
                if det.owngroup_name == group.group_name:
                    dets.append(det)
            if dets != []:
                new_ext = Extender(
                    self.timer,
                    group,
                    dets,
                    self.ext_groups,
                    e3dets,
                    ext_params,
                )
                self.extenders.append(new_ext)

        ext_cnf = options.get("extenders")

        # DBIK240803 Create e3extenders based on e3detectors
        for group in self.groups:
            dets = []
            qdets = []
            e3dets = []
            ext_params = {}

            if ext_cnf is not None:
                for key in ext_cnf:
                    grp = ext_cnf[key]["group"]
                    if grp == group.group_name:
                        ext_params = ext_cnf[key]

            for e3det in self.e3detectors:
                if e3det.owngroup_name == group.group_name:
                    e3dets.append(e3det)

            if e3dets != []:
                new_ext = e3Extender(self.timer, group, dets, qdets, e3dets, ext_params)
                self.e3extenders.append(new_ext)

        if self.print_status:
            print("---------------------------------------------------------------")
            print("Requesting e1 detecotrs set:  ")
            print(self.req_dets)
            print("Extending e1 detectors set:  ")
            print(self.ext_dets)
            print("Extending signal groups set:  ")
            print(self.ext_groups)
            print("e1 Extenders set: ")
            print(self.extenders)
            print("e3 Extenders set: ")
            print(self.e3extenders)
            print("---------------------------------------------------------------")

            self.print_controller_params()

        self.set_delay_groups()  # DBIK231208  Start delays configuration

        self.set_side_requests()  # DBIK231214 Side requests configuration

        if self.print_status:
            print("____")

        self.state = "Scan"
        self.prev_phase_order_str = ""

    @property
    def id(self) -> str:
        """ID of the signal controller."""
        return self.name

    def reset(self) -> None:
        """Reset the timer to its original options."""
        self.timer.reset()
        self.__init__(self.name, self._options, self.timer)

    def reload(self) -> None:
        """Reload the timer from its original options."""
        return self.reset()

    def save(self, filename: str) -> None:
        """Save controllers configuration to a file."""
        return self.save_conf(filename)

    def all_red(self) -> None:
        """Gracefully transition to all red phase and stay there until reset."""
        raise NotImplementedError("PhaseRingController does not implement all red.")

    @property
    def status(self) -> ControllerStatus:
        """Controller status as an object."""
        return ControllerStatus(
            0,
            str(self.current_main_phase) if self.current_main_phase else "",
            str(self.next_main_phase) if self.next_main_phase else "",
        )

    @property
    def status_dict(self) -> dict[str, Any]:
        """Controller status as a dictionary."""
        status = self.status

        return {
            "step_count": status.step_count,
            "current_phase": status.current_phase,
            "next_phase": status.next_phase,
        }

    @property
    def signal_states(self) -> str:
        """Current signal states in Open Controller format."""
        states = [grp.get_grp_state() for grp in self.groups]
        return "".join(states)

    @property
    def signal_states_sumo(self) -> str:
        """Current signal states in SUMO format."""
        states = [grp.get_sumo_state() for grp in self.groups]
        return "".join(states)

    def tick(self):
        """This is the clocking function moving the group states and system timer
        And in effect the phasing (timing depenmds on group operations)
        """
        # extension is based on this
        for det in self.ext_dets:
            det.tick()  # testing git branch 3

        # Sets the detector requests, if reset in previus cycle
        for det in self.req_dets:
            det.tick()

        # DBIK240821 Updates the Multi-Entry/Exit (e3) Detectors
        for det in self.e3detectors:
            det.tick()

        for grp in self.groups:
            grp.prev_state = grp.state  # DBIK20231013 Save the previous states

        for grp in self.groups:
            if grp.extender:
                grp.extender.tick()  # DBIK230331 The extender update moved here
            if grp.e3extender:
                grp.e3extender.tick()  # DBIK240803 The e3extender update added

            grp.tick()

        self.update_states()  # No more using the state machine

    def find_the_next_main_phase(self) -> SimplePhase | None:
        """Find the next phase with an active request using round-robin."""
        # Rotate phase ring so search starts at the current phase
        if self.current_main_phase in self.main_phases:
            split_idx = self.main_phases.index(self.current_main_phase)
            phase_order = self.main_phases[split_idx:] + self.main_phases[:split_idx]
        else:
            phase_order = list(self.main_phases)

        # Find the first phase in the rotated ring with an active request
        next_phase = next(
            (phase for phase in phase_order if phase.phase_has_a_request()),
            None,
        )

        # Construct status debug string
        phases_formatted = " ".join(str(phase) for phase in phase_order)
        phase_order_str = (
            f"{self.timer.seconds} {self.name} phase order: {phases_formatted} "
            f", curPH: {self.current_main_phase}, nextPH: {next_phase}"
        )

        if phase_order_str != self.prev_phase_order_str:
            if self.print_status:
                pass  # Retained commented/pass logic from original code
            self.prev_phase_order_str = phase_order_str

        return next_phase

    def update_states(self) -> None:
        """Scan for next phase requests and manage state transitions."""
        if self.state == "Scan":
            self.next_main_phase = self.find_the_next_main_phase()
            if self.next_main_phase:
                self.next_main_phase.set_signalgroup_green_permissions(do_permit=True)

        # 2. Reset green permits and priority levels for groups in min green
        for group in self.groups:
            if group.is_in_min_green():
                group.permit_green = False
                if group.own_request_level > 2:
                    group.own_request_level = 2  # Reset priority request
                    for conflict in group.conflicting_groups:
                        # Reset conflict group priority request
                        conflict["group"].other_request_level = 2

        # 3. Transition to 'Hold' state once the next phase has started
        if self.next_main_phase and self.next_main_phase.phase_has_started():
            self.current_main_phase = self.next_main_phase
            self.next_main_phase = None
            self.state = "Hold"

            if self.print_status:
                print(
                    f"{self.timer.seconds}s {self.name} "
                    f"NEW PHASE STARTED: {self.current_main_phase}",
                )

        # 4. Maintain green permissions during 'Hold' until all min times expire
        if self.state == "Hold" and self.current_main_phase:
            self.current_main_phase.set_signalgroup_green_permissions(do_permit=True)

            if self.current_main_phase.all_min_greens_have_ended():
                self.state = "Scan"
                if self.print_status:
                    print(
                        f"{self.timer.seconds}s {self.name} "
                        f"ALL MIN TIMES ENDED: {self.current_main_phase}",
                    )

    def get_control_status(self, max_len: int = 40) -> str:
        """Return formatted single-line status info (time, phase, group states, requests, E3 detectors)."""
        # Debug Output Toggles (converted from the original author's hacky string flags)
        det_mode = "req"  # Options: "loop", "req", "reqprio", None
        ext_mode = "group"  # Options: "group", "det", None
        show_perm = False  # Formerly "perm_" (Disabled)
        cut_mode = (
            None  # Formerly "prio2_" (Disabled; Options: "cut", "prio1", "prio2", None)
        )
        show_e3_cnt = True  # Formerly "e3Cnt"
        show_e3_conf = False  # Formerly "e3confCnt_" (Disabled)
        e3_ext_mode = "e3crit2"  # Options: "e3crit", "e3crit2", None

        status_parts: list[str] = []

        # 1. Base Signal States (inserts space every 5 chars)
        sig_raw = str(self.get_grp_states())
        sig_formatted = "".join(
            f" {char}" if i % 5 == 0 else char for i, char in enumerate(sig_raw)
        )
        status_parts.append(sig_formatted[:max_len])

        # 2. Detector / Request Status
        if det_mode == "loop":
            loops = "".join("1" if det.loop_on else "0" for det in self.req_dets)
            status_parts.append(f"LOOP:{loops[:30]}")
        elif det_mode in ("req", "reqprio"):
            req_chars = []
            for i, group in enumerate(self.groups):
                if i % 5 == 0:
                    req_chars.append(" ")
                if group.request_green:
                    req_chars.append(
                        str(group.own_request_level) if det_mode == "reqprio" else "1",
                    )
                else:
                    req_chars.append("0")
            status_parts.append(f"REQ:{''.join(req_chars)[:max_len]}")

        # 3. Extension Status
        if ext_mode == "group":
            ext_chars = []
            for i, group in enumerate(self.groups):
                if i % 5 == 0:
                    ext_chars.append(" ")
                if group.extender or group.e3extender:
                    if group.extender:
                        ext_chars.append(
                            "1" if (group.extender.extend and group.group_on) else "0",
                        )
                    if group.e3extender:
                        ext_chars.append(
                            "2"
                            if (group.e3extender.extend and group.group_on)
                            else "0",
                        )
                else:
                    ext_chars.append("X")
            status_parts.append(f"EXT:{''.join(ext_chars)[:max_len]}")
        elif ext_mode == "det":
            dext = "".join("1" if det.is_extending() else "0" for det in self.ext_dets)[
                :max_len
            ]
            qext = "".join(
                "1" if gdet.is_extending() else "0" for gdet in self.ext_groups
            )[:max_len]
            status_parts.append(f"DEXT: {dext} QEXT: {qext}")

        # 4. Permission Status
        if show_perm:
            perm_chars = [
                f"{' ' if i % 5 == 0 else ''}{'1' if g.permit_green else '0'}"
                for i, g in enumerate(self.groups)
            ]
            status_parts.append(f"PERM:{''.join(perm_chars)[:max_len]}")

        # 5. Cut / Priority Status
        if cut_mode:
            cut_chars = []
            for i, group in enumerate(self.groups):
                if i % 5 == 0:
                    cut_chars.append(" ")
                if cut_mode == "cut":
                    cut_chars.append(
                        "1" if group.end_conflicting_greens_status() else "0",
                    )
                elif cut_mode == "prio1":
                    active = group.end_conflicting_greens_status() and group.group_on()
                    cut_chars.append(str(group.other_request_level) if active else "0")
                elif cut_mode == "prio2":
                    cut_chars.append(str(group.other_request_level))

            prefix = "PRI:" if cut_mode.startswith("prio") else "CUT:"
            status_parts.append(f"{prefix}{''.join(cut_chars)[:max_len]}")

        # 6. Current & Next Phase Info + Controller State
        phase_info = f"(cur:{self.current_main_phase}, next:{self.next_main_phase})"
        if self.state == "Scan":
            phase_info += " S"
        elif self.state == "Hold":
            phase_info += " H"
        status_parts.append(phase_info)

        # 7. E3 Detector Vehicle Counts
        if show_e3_cnt:
            counts = ",".join(str(det.veh_count()) for det in self.e3detectors)
            status_parts.append(f"vehs: {counts[:max_len]}")

        # 8. E3 Extender Conflict Counts
        if show_e3_conf:
            conflicts = ",".join(str(ext.conf_sum) for ext in self.e3extenders)
            status_parts.append(f"conf: {conflicts[:max_len]}")

        # 9. E3 Critical Ratio Analysis
        if e3_ext_mode == "e3crit":
            ratios = [
                f"{round(ext.vehcount / ext.conf_sum, 2) if ext.conf_sum > 0 else -1},"
                for ext in self.e3extenders
                if ext.extend
            ]
            status_parts.append(f"e3rel: {''.join(ratios)}")

        elif e3_ext_mode == "e3crit2":
            se_entries = []
            for idx, group in enumerate(self.groups, start=1):
                if group.e3extender and group.get_grp_state() in ["5"]:
                    e3 = group.e3extender
                    v_count = e3.vehcount
                    conf_val = 1.0 if e3.ext_mode == 1 else e3.conf_sum
                    threshold = round(e3.threshold, 1)
                    ratio = round(v_count / conf_val, 1) if conf_val > 0 else 10.0
                    cmp_op = ">" if ratio > threshold else "<"

                    se_entries.append(
                        f"{idx}: {v_count}/{conf_val} {ratio}{cmp_op}{threshold}|",
                    )
            if se_entries:
                status_parts.append(f"SE: |{''.join(se_entries)}")

        return " ".join(status_parts)

    def start_a_new_phase(self):
        self.current_main_phase = self.next_main_phase
        self.next_main_phase = None
        if self.print_status:
            print("NEW PHASE STARTED:", self.current_main_phase)

    def next_phase_selected(self):
        if self.print_status:
            print("NEXT PHASE FIXED: ", self.next_main_phase)

    #
    # State transfer conditions
    #

    def curr_phase_a_min_green_ended(self):
        """Returns true if any min green has passed
        by any of the groups in _current_ phase
        """
        if self.current_main_phase:
            return self.current_main_phase.one_min_green_has_ended()

        return False

    def next_phase_a_green_started(self):
        """Returns true if a green has been started
        by any of the groups in _next_ phase
        """
        if self.next_main_phase:
            # return self.next_main_phase.green_has_started()
            return (
                self.next_main_phase.green_has_started()
            )  # DBIK231129 Phase starts if any group at IG or Amber

        return False

    def curr_phase_active_greens_ended(self):
        """Returns true if there is no active green extension
        by any of the groups in _current_ phase
        """
        if self.current_main_phase:
            return self.current_main_phase.all_active_greens_have_ended()

        return False

    #
    # Controller operation
    #
    #
    # Init Functions
    #

    def set_conflict_groups(self, intergreens):
        """We set the conflicting groups
        These are based on intergreen matrix
        """
        # clear the previous conflicts
        for grp in self.groups:
            grp.conflicting_groups = []
            grp.non_conflicting_groups = []

        # FIXME: the naming is stupid, intergreens is used in the loop and means different thing
        for to_grp, intergreens in zip(self.groups, intergreens):
            # If there is integreen time from a group to this group (to_group)
            # We add this conflict to group
            for from_grp, intergreen in zip(self.groups, intergreens):
                if not intergreen == 0.0:
                    to_grp.add_conflicting_group(from_grp, delay=intergreen)
                else:
                    to_grp.add_non_conflicting_group(
                        from_grp,
                        delay=intergreen,
                    )  # DBIK 230915 add to the list of non conflicting groups

    def set_side_requests(self):
        """Set groups that will be requested, if this group gets request"""
        if self.print_status:
            print("Find side requests: ")
        for grp in self.groups:
            if "side_requests" in grp.grp_conf:
                sidereqs = grp.grp_conf["side_requests"]
                if sidereqs:
                    for sgrp_name in sidereqs:
                        sgrp = self.get_signal_group_object(sgrp_name)
                        grp.side_requests.append(sgrp)
                    if self.print_status:
                        print(
                            "Group:",
                            grp.group_name,
                            ", Side requests: ",
                            grp.side_requests,
                        )

    def set_delay_groups(self):
        """Set groups that need to be waited"""
        if self.print_status:
            print("Find delay groups: ")
        for grp in self.groups:
            dd = self.get_delay_dictionary(grp)
            delgroups = self.set_starting_delays(grp, dd)
            if delgroups:
                for dgrp in delgroups:
                    grp.delaying_groups.append(dgrp)
                    dgrp.disabling_groups.append(grp)
                if self.print_status:
                    print(
                        "Group:",
                        grp.group_name,
                        ", Delay groups: ",
                        grp.delaying_groups,
                        "Disable groups: ",
                        dgrp.disabling_groups,
                    )

    def get_delay_dictionary(self, grp):
        if "delaying_groups" in grp.grp_conf:
            return grp.grp_conf["delaying_groups"]
        return None

    def set_starting_delays(self, grp, deldict):
        delgroups = []
        if not deldict:
            return None
        for delgroupname in deldict:
            delgroup = self.get_signal_group_object(delgroupname)
            delgroups.append(delgroup)
        return delgroups

    def get_signal_group_object(self, grpname):
        """Returns signal group object based on name"""
        for grp in self.groups:
            if grp.group_name == grpname:
                return grp
        return None

    def set_phase_ring(self, phase_ring):
        """Defines the phase ring based on tuple of tuples (ie phase ring matrix)"""
        self.main_phases = []
        ph_index = 1
        for row in phase_ring:
            groups_in_mp = []
            for grp, ph_stat in zip(self.groups, row):
                if ph_stat == 1:
                    groups_in_mp.append(grp)
            new_main_phase = SimplePhase(ph_index, groups_in_mp, self.timer)
            if self.print_status:
                print("Phase: ", ph_index, " ", groups_in_mp)
            ph_index += 1
            self.main_phases.append(new_main_phase)
        self.current_main_phase = None  # we are not in any main phase
        self.next_main_phase = None  # Next scheduled main phase

    # This is for mapping one controller for many sumo signalheads
    def set_sumo_outputs(self, grouplist):
        """Overrides sumo outputlist defined in init"""
        groups = []
        for grp_name in grouplist:
            for grp in self.groups:
                if grp.group_name == grp_name:
                    if self.print_status:
                        print("FOUND:", grp_name)
                    groups.append(grp)
        if len(groups) == len(grouplist):
            self.sumo_outputs = groups
        else:
            print("WARNING: some sumo groups not found")

    #
    # Conf functions
    #

    def get_conf_as_dict(self):
        """Returns controller conf file as dictionary"""
        conf = {}
        conf["controller"] = {}
        conf["controller"]["name"] = "test"  # self.name

        # Signal groups
        conf["controller"]["signal_groups"] = {}
        for group in self.groups:
            conf["controller"]["signal_groups"][group.group_name] = group.get_params()

        # Detectors
        conf["controller"]["detectors"] = {}
        for det in self.req_dets:
            conf["controller"]["detectors"][det.name] = det.get_params()
        for det in self.ext_dets:
            conf["controller"]["detectors"][det.name] = det.get_params()
        for det in self.ext_groups:
            conf["controller"]["detectors"][det.name] = det.get_params()

        # group IDs
        conf["controller"]["group_list"] = self.group_ids

        # phases
        conf["controller"]["phases"] = []
        for phase in self.get_phases():
            conf["controller"]["phases"].append(list(phase))

        # Intergreens
        ig_tuples = self.get_intergreens()
        intergreens = []
        for from_group in ig_tuples:
            intergreens.append(list(from_group))
        conf["controller"]["intergreens"] = intergreens
        return conf

    def process_new_conf(self, new_conf):
        """This is for processing new conf-coming from the UI as a dictionary"""
        if "controller" not in new_conf:
            return "No controller in conf"

        # Signal groups
        if "signal_groups" not in new_conf["controller"]:
            return "No signal_groups in conf"
        for conf_group in new_conf["controller"]["signal_groups"]:
            for group in self.groups:
                if group.group_name == conf_group:
                    group.set_params(
                        new_conf["controller"]["signal_groups"][conf_group],
                    )

        # Intergreens, Note: this has not been tested in practice
        if "intergreens" not in new_conf["controller"]:
            return "No intergreens in conf"
        new_intergreens = []
        for from_group in new_conf["controller"]["intergreens"]:
            new_intergreens.append(tuple(from_group))
        intergreens = tuple(new_intergreens)
        self.set_conflict_groups(intergreens)

        return "Ok"

    def save_conf(self, filename: str) -> None:
        """Save the controller conf to a file."""
        conf = self.get_conf_as_dict()
        with open(filename, "w") as outfile:
            json.dump(conf, outfile, indent=4)

    def read_conf(self, filename) -> dict[str, Any]:
        """Read the controller conf from a file."""
        with open(filename) as json_file:
            conf = json.load(json_file)
        self.process_new_conf(conf)
        return conf

    #
    # Print and export functions
    #

    def print_controller_params(self) -> None:
        """Print basic controller set up."""
        print("Controller:", self.name)
        print("\nPHASE RING")
        for phase in self.get_phases():
            print(phase)

        # Maybe at group ids here?
        print("\nINTERGREENS")
        for to_group in self.get_intergreens():
            print(to_group)

        print("\nGROUPS")
        print(self.groups)

        print("\nREQUEST DETS")
        print(self.req_dets)

        print("\nEXTENDING DETS")
        print(self.ext_dets)

        print("\nEXTENDING GROUPS")
        print(self.ext_groups)

        print("\nEXTENDERS")
        print(self.extenders)

        print("\nCONFLICT MATRIX")
        conflicts = self.get_conflict_matrix()
        for conflict_row in conflicts:
            print(conflict_row)

        print("\nMAIN PHASES")
        for mp in self.main_phases:
            print(mp)
        print(self.main_phases)  # DBIK 20231010

        print("___")

    def get_conflict_matrix(self) -> tuple[tuple[int, ...]]:
        """Get the conflict matrix as tuple."""
        matrix = []
        for y in self.groups:
            line = []
            for x in self.groups:
                if y.group_in_conflict(x):
                    line.append(1)
                else:
                    line.append(0)
            matrix.append(tuple(line))
        return tuple(matrix)

    def get_intergreens(self) -> tuple[tuple[float, ...]]:
        """Get the intergreen matrix as a tuple."""
        intergreens = []
        group_count = len(self.groups)
        for group in self.groups:
            blocking = [0.0] * group_count  # by default, no intergreens
            for conflicting in group.conflicting_groups:
                index = self.groups.index(conflicting["group"])
                blocking[index] = conflicting["delay"]
            intergreens.append(tuple(blocking))

        return tuple(intergreens)

    def get_phases(self) -> tuple[tuple[int, ...]]:
        """Get the phase ring as a tuple."""
        phases = []
        for phase in self.main_phases:
            phase_row = []
            for group in self.groups:
                if group in phase.groups:
                    phase_row.append(1)
                else:
                    phase_row.append(0)
            phases.append(tuple(phase_row))
        return tuple(phases)

    #
    # Output functions
    #
    def get_OC_status_short(self):
        status = {}
        status["step_count"] = self.timer.steps
        status["current_phase"] = str(self.current_main_phase)
        status["next_phase"] = str(self.next_main_phase)
        return status

    def get_status_as_dict(self):
        status = {}
        status["step_count"] = self.timer.steps
        status["group_states"] = self.get_grp_states()
        status["current_phase"] = str(self.current_main_phase)
        status["next_phase"] = str(self.next_main_phase)

        ext_stat = ""
        for grp in self.groups:
            if grp.extender:
                if grp.extender.extend:
                    ext_stat += "1"
                else:
                    ext_stat += "0"
            else:
                ext_stat += "N"
        status["extender_states"] = ext_stat
        req_stat = ""
        for grp in self.groups:
            if grp.request_green:
                req_stat += "1"
            else:
                req_stat += "0"
        status["request_states"] = req_stat

        return status

    def get_grp_states(self):
        """Returns group statuses as string in traditional format"""
        sstats = ""

        for grp in self.groups:
            sstats += grp.get_grp_state()

        return sstats

    def get_sumo_states(self):
        """Returns group statuses as string Sumo-format"""
        sstats = ""

        for grp in self.sumo_outputs:
            sstats += grp.get_sumo_state()

        return sstats

    #
    # UI functions
    #

    def get_group_params_as_df(self):
        """Returns group params as pandas dataframe"""
        all_groups = {}
        for group in self.groups:
            # print("Name", group.name, "Params:",  group.get_params())
            params = group.get_params()
            all_groups[group.name] = params
        if self.print_status:
            print(all_groups)
        df = pd.DataFrame(all_groups)

        df = df.transpose()
        cols = df.columns.tolist()
        cols.pop(cols.index("name"))
        cols = ["name", cols]
        return df.reindex(columns=cols)

    def get_lane_params_as_df(self):
        """Returns lane params as pandas dataframe"""
        all_lanes = {}

        if not self.lanes:
            return pd.DataFrame(
                all_lanes,
            )  # If lanes are not defined, return empty dataframe

        for lane in self.lanes:
            params = lane.get_params()
            # We remove the coodintaes, since we don't want to show them
            if "coordinates" in params:
                params.pop("coordinates")
            # we convert users as string, since we want a simplified UI
            if "users" in params:
                users = params["users"]
                params["users"] = str(users)
            all_lanes[lane.id] = params
        df = pd.DataFrame(all_lanes)
        df = df.transpose()
        cols = df.columns.tolist()
        cols.pop(cols.index("id"))
        # cols = ["id"] + cols
        df = df.reindex(columns=cols)
        return df

    def get_intergreens_as_df(self):
        """Returns intergreen matrix as pandas dataframe"""
        intergreen_table = {}

        # Note, the matrix order is based on the group list
        for to_grp, intergreens in zip(self.groups, self.get_intergreens()):
            to_name = to_grp.group_name
            new_row = {}
            new_row["Starting group"] = to_name
            for from_grp, intergreen in zip(self.groups, intergreens):
                from_name = from_grp.group_name
                new_row[from_name] = intergreen
            intergreen_table[to_name] = new_row

        df = pd.DataFrame(intergreen_table)

        df = df.transpose()
        cols = df.columns.tolist()
        cols.pop(cols.index("Starting group"))
        cols = ["Starting group"] + cols
        df = df.reindex(columns=cols)
        return df

    def get_phases_as_df(self):
        """Returns the phase ring as pandas dataframe"""
        phase_table = {}
        phase_id = 1
        for phase in self.get_phases():
            new_row = {}
            new_row["Phase"] = phase_id
            for group, val in zip(self.groups, phase):
                new_row[group.group_name] = val
            phase_name = "Phase " + str(phase_id)
            phase_table[phase_name] = new_row
            phase_id += 1
        df = pd.DataFrame(phase_table)
        df = df.transpose()
        cols = df.columns.tolist()
        cols.pop(cols.index("Phase"))
        df = df.reindex(columns=cols)

        return df

    def update_group_params(self, new_params):
        """Receives group params from the UI as list of dictonaries and updates them"""
        # Note: now sure how to make sanity check for these
        for new_param in new_params:
            for group in self.groups:
                if group.group_name == new_param["name"]:
                    errors = group.set_params(new_param)
                    if errors:
                        return errors
        return None  # No errors

    def update_ig_params(self, new_params):
        """Receives intergreen params from the UI as list of dictonaries and updates them"""
        # Note: now sure how to make sanity check for these
        new_intergreens = []
        for row in new_params:
            blocking = []
            ig_values = list(row.values())
            ig_values.pop(0)  # remove the index

            for ig_val in ig_values:
                if not value_is_number(ig_val):
                    return "Non-numeric value in intergreen matrix"
                blocking.append(float(ig_val))
            new_intergreens.append(tuple(blocking))
        new_intergreens = tuple(new_intergreens)
        self.set_conflict_groups(new_intergreens)

        return None  # No errors

    # Note: this doesn't work yet, we get too mixed up ehen phases are changed midway
    # Likely an all red phase is needed
    def update_phase_params(self, new_params):
        """Receives intergreen params from the UI as list of dictonaries and updates them"""
        # Note: now sure how to make sanity check for these
        new_phases = []
        for row in new_params:
            on_groups = list(row.values())
            new_on_groups = []
            for on_group in on_groups:
                if not (
                    on_group == 1 or on_group == 0 or on_group == "1" or on_group == "0"
                ):
                    return "Only ones and zeroes allowed in phase matrix"
                new_on_groups.append(int(on_group))
            new_phases.append(tuple(new_on_groups))
        new_phases = tuple(new_phases)
        self.set_phase_ring(new_phases)
        return None  # No errors
