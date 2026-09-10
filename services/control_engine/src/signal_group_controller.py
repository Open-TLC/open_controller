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

import json
from typing import Any

from services.control_engine.src.detectors.area_detector import AreaDetector
from services.control_engine.src.detectors.point_detector import PointDetector
from services.control_engine.src.extenders.extender import Extender
from services.control_engine.src.extenders.gap_seeking_extender import (
    GapSeekingExtender,
)
from services.control_engine.src.extenders.smart_extender import SmartExtender
from services.control_engine.src.requesters.presence_requester import PresenceRequester
from services.control_engine.src.requesters.requester import Requester
from services.control_engine.src.requesters.trigger_requester import TriggerRequester

from .signal_controller import ControllerStatus, SignalController
from .signal_group import SignalGroup
from .timer import Timer

OC_TO_SUMO_MAP: dict[str, str] = {
    "a": "r",  # Red Minimum Time
    "b": "r",  # Red Wait Request & Permission
    "f": "r",  # Red Ending Conflicts
    "g": "r",  # Red Wait Intergreen
    "0": "u",  # Amber-Red
    "1": "g",  # Green Minimum Time
    "5": "g",  # Green Extending
    "4": "g",  # Green Passive/Remain Green
    "<": "y",  # Amber
}


class PhaseRingController(SignalController):
    """Signal controller operating with flexible phase-ring group control."""

    def __init__(
        self,
        controller_id: str,
        options: dict[str, Any],
        timer: Timer,
        detectors: list[AreaDetector | PointDetector],
    ) -> None:
        self._id: str = controller_id
        self._timer: Timer = timer
        self._options: dict[str, Any] = options
        self._detectors: list[AreaDetector | PointDetector] = detectors
        self._print_status: bool = bool(options.get("print_status", False))

        # sumo_outputs is a list of signal group IDs. The SUMO signal string should be
        # pieced together from signal group states in this order.
        self._sumo_outputs: list[str] = options.get("sumo_outputs", [])

        self._group_ids: list[str] = options["group_list"]

        phase_ring: list[list[int]] = options.get("phases", [])

        intergreen_matrix = options["intergreens"]

        if len(phase_ring[0]) != len(self._group_ids):
            raise ValueError(
                f"Group count mismatch: Phase ring has {len(phase_ring[0])}, "
                f"group_list has {len(self._group_ids)}",
            )

        # Build intergreens lookup dictionary per group ID
        intergreens_by_group: dict[str, dict[str, float]] = {
            gid: {
                other_id: float(intergreen_matrix[i][j])
                for j, other_id in enumerate(self._group_ids)
            }
            for i, gid in enumerate(self._group_ids)
        }

        # Initialize SignalGroups with mandatory intergreens dict
        self._groups: list[SignalGroup] = [
            SignalGroup(
                self._timer,
                group_id,
                group_options,
                intergreens_by_group[group_id],
            )
            for group_id, group_options in options["signal_groups"].items()
        ]

        self._groups_by_id: dict[str, SignalGroup] = {g.id: g for g in self._groups}

        # Wire inter-group conflicts and extenders
        self._set_conflict_groups(intergreen_matrix)
        extenders_by_group = self._create_extenders(
            options.get("extenders", []),
            detectors,
        )
        requesters_by_group = self._create_requesters(
            options.get("requesters", []),
            detectors,
        )

        for group in self._groups:
            group.add_extenders(extenders_by_group.get(group.id, []))
            group.add_requesters(requesters_by_group.get(group.id, []))

        self._phases: list[list[SignalGroup]] = self._get_groups_by_phase(phase_ring)

        # Initially the controller is locked to the first phase. It will then start
        # transitioning all groups in that phase to green.
        self._state: str = "locked"
        self._current_phase_idx: int = 0
        self._next_phase_idx: int | None = None
        self._last_print_data = ""
        self._last_print_time = 0

    @property
    def id(self) -> str:
        """ID of the signal controller."""
        return self._id

    def reset(self) -> None:
        """Reset controller and internal timer."""
        self._timer.reset()
        self.__init__(self._id, self._options, self._timer, self._detectors)

    def reload(self) -> None:
        """Reload configuration state."""
        self.reset()

    def save(self, filename: str) -> None:
        """Save configuration dictionary to file."""
        conf = self.get_conf_as_dict()
        with open(filename, "w") as outfile:
            json.dump(conf, outfile, indent=4)

    def all_red(self) -> None:
        """Safely transition to all groups red state."""
        raise NotImplementedError("PhaseRingController does not implement all_red.")

    @property
    def status(self) -> ControllerStatus:
        """Controller's internal status as an object."""
        return ControllerStatus(
            self._timer.steps,
            str(self._current_phase_idx),
            str(self._next_phase_idx) if self._next_phase_idx else "",
        )

    @property
    def status_dict(self) -> dict[str, Any]:
        """Controller's internal status as a dictionary."""
        st = self.status
        return {
            "step_count": st.step_count,
            "current_phase": st.current_phase,
            "next_phase": st.next_phase,
        }

    @property
    def signal_states(self) -> str:
        """Return signal states in Open Controller format."""
        return "".join(grp.signal_state for grp in self._groups)

    @property
    def signal_states_sumo(self) -> str:
        """Return signal states mapped to SUMO formatting."""
        return "".join(
            OC_TO_SUMO_MAP.get(self._groups_by_id[grp_id].signal_state, "r")
            for grp_id in self._sumo_outputs
        )

    def tick(self) -> None:
        """Advance all signal groups and process phase transitions."""
        states_out = ""
        grp_no = 1
        for grp in self._groups:
            grp.tick()
            states_out += grp.signal_state
            if grp_no % 5 == 0:
                states_out += " "
            grp_no += 1

        if self._state == "minimum":
            self._tick_minimum()
        elif self._state == "locked":
            self._tick_locked()
        elif self._state == "transition":
            self._tick_transition()

        _print_data = f"{'State:'}{self._state:<15} Cur: {str(self._current_phase_idx)} Next: {str(self._next_phase_idx):<5} Sig: {states_out}"

        _print_time = round(self._timer.seconds, 1)

        if (_print_time - self._last_print_time >= 1.0) or (
            _print_data != self._last_print_data
        ):
            print(f"Time: {_print_time:<8}{_print_data}")
            self._last_print_data = _print_data
            self._last_print_time = _print_time

    def _tick_minimum(self) -> None:
        groups_in_minimum: bool = any(
            grp.signal_state in {"f", "g", "0", "1"}  # DBIK20260910 added state "f"
            for grp in self._phases[self._current_phase_idx]
        )
        # Do not advance, until all groups have started their greens and
        # cleared their minimum times.
        if groups_in_minimum:
            return

        next_phase_idx = self._find_next_phase_idx()

        # Only advance if a new phase is found.
        if next_phase_idx is None:
            return

        self._next_phase_idx = next_phase_idx
        self._state = "locked"

    def _tick_locked(self) -> None:
        if self._next_phase_idx is None:
            self._state = "minimum"
            return

        # Check if a requesting group in next phase can start.
        for group in self._phases[self._next_phase_idx]:
            has_request = group.is_requesting
            can_start = not any(
                grp.signal_state
                in {"f", "g", "0", "1", "5"}  # DBIK20260910 added states "f" and "g"
                for grp in group.conflict_groups
            )

            # If such group is found, the group is given a green permission and
            # controller advances to transition mode.
            if has_request and can_start:
                group.give_green_permission()
                self._current_phase_idx = (
                    self._next_phase_idx
                    if self._next_phase_idx is not None
                    else self._current_phase_idx
                )
                self._next_phase_idx = None
                self._state = "transition"

    def _tick_transition(self) -> None:
        num_groups_waiting: int = 0

        for group in self._phases[self._current_phase_idx]:
            has_request = group.is_requesting
            can_start = not any(
                grp.signal_state in {"0", "1", "5"} for grp in group.conflict_groups
            )

            # Requesting group in current phase is still waiting for conflicts to end
            # active green.
            if has_request and not can_start:
                num_groups_waiting += 1

            # Requesting group in current phase is started when possible.
            elif has_request and can_start:
                group.give_green_permission()

        # Controller can advance, once no requesting groups in the current phase are
        # waiting for their green to start.
        if num_groups_waiting == 0:
            self._state = "minimum"

    def _find_next_phase_idx(self) -> int | None:
        """Find the index of the next phase with a green request."""
        if not self._phases:
            return None

        num_phases = len(self._phases)
        # Start checking immediately after current phase
        # (or at 0 if no phase is current)
        start_offset = (
            (self._current_phase_idx + 1) if self._current_phase_idx is not None else 0
        )

        for offset in range(num_phases):
            idx = (start_offset + offset) % num_phases
            if any(group.is_requesting for group in self._phases[idx]):
                return idx

        return None

    def _set_conflict_groups(self, intergreen_matrix: list[list[float]]) -> None:
        """Assign conflicting signal groups based on the intergreen matrix."""
        for i, grp in enumerate(self._groups):
            conflicts = [
                self._groups[j]
                for j, delay in enumerate(intergreen_matrix[i])
                if delay > 0.0
            ]
            grp.add_conflict_groups(conflicts)

    def _get_groups_by_phase(
        self,
        group_phase_mapping: list[list[int]],
    ) -> list[list[SignalGroup]]:
        """Assign groups to phases according to group phase mapping."""
        group_indices_by_phase: list[list[int]] = [
            [i for i, val in enumerate(sublist) if val == 1]
            for sublist in group_phase_mapping
        ]

        groups_by_phase: list[list[SignalGroup]] = []

        for group_indices in group_indices_by_phase:
            groups: list[SignalGroup] = []
            for index in group_indices:
                group_id: str = self._group_ids[index]
                group: SignalGroup = self._groups_by_id[group_id]
                groups.append(group)
            groups_by_phase.append(groups)

        return groups_by_phase

    def _create_extenders(
        self,
        extender_options: list[dict[str, Any]],
        detectors: list[AreaDetector | PointDetector],
    ) -> dict[str, list[Extender]]:
        """Instantiate extenders mapped by group ID."""
        extenders: dict[str, list[Extender]] = {}
        for opts in extender_options:
            e_type = str(opts.get("type"))
            group_id = str(opts.get("group", ""))
            if not group_id:
                raise ValueError(
                    f"Extender {opts.get('id')} missing group in controller {self.id}",
                )

            if e_type == "gap_seeking":
                extender: Extender = GapSeekingExtender(
                    str(opts.get("id")),
                    self._timer,
                    opts["options"],
                    detectors,
                )
            elif e_type == "smart":
                grp = self._groups_by_id[group_id]
                conflicting_ids = [c.id for c in grp.conflict_groups]
                conflicting_dets: list[str] = [
                    d
                    for other in extender_options
                    if other.get("type") == "smart"
                    and other.get("group") in conflicting_ids
                    for d in other.get("options", {}).get("detectors", [])
                ]
                extender = SmartExtender(
                    str(opts.get("id")),
                    self._timer,
                    opts["options"],
                    conflicting_dets,
                    detectors,
                    lambda g=grp: g.green_started_at,
                )
            else:
                raise ValueError(
                    f"Unknown extender type {e_type} in controller {self.id}",
                )

            extenders.setdefault(group_id, []).append(extender)

        return extenders

    def _create_requesters(
        self,
        requester_options: list[dict[str, Any]],
        detectors: list[AreaDetector | PointDetector],
    ) -> dict[str, list[Requester]]:
        """Intantiante requesters mapped by group ID."""
        requesters: dict[str, list[Requester]] = {}
        for opts in requester_options:
            r_type = str(opts.get("type"))
            r_id = str(opts.get("id", ""))
            group_id = str(opts.get("group", ""))

            requester: Requester

            if r_type == "presence":
                requester = PresenceRequester(r_id, opts["options"], detectors)
            elif r_type == "trigger":
                grp = self._groups_by_id[group_id]
                requester = TriggerRequester(
                    r_id,
                    opts["options"],
                    lambda g=grp: g.is_blocking,
                    detectors,
                )
            else:
                raise ValueError(
                    f"Unknown requester type {r_type} for requester with ID {r_id}",
                )

            requesters.setdefault(group_id, []).append(requester)

        return requesters

    def get_conf_as_dict(self) -> dict[str, Any]:
        """Return full controller configuration dictionary."""
        return {
            "controller": {
                "name": self.id,
                "group_list": self._group_ids,
                "phases": [
                    [1 if g in p.groups else 0 for g in self._groups]
                    for p in self.main_phases
                ],
                "intergreens": [
                    [
                        self._options["intergreens"][i][j]
                        for j in range(len(self._groups))
                    ]
                    for i in range(len(self._groups))
                ],
            },
        }
