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

from .phase import SimplePhase
from .signal_controller import ControllerStatus, SignalController
from .signal_group import SignalGroup
from .timer import Timer

OC_TO_SUMO_MAP: dict[str, str] = {
    "a": "r",  # Red Minimum Time
    "b": "r",  # Red Wait Request & Permission
    "f": "r",  # Red Ending Conflicts
    "g": "r",  # Red Wait Intergreen
    "0": "u",  # Amber-Red
    "1": "G",  # Green Minimum Time
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

        self._group_ids: list[str] = options["group_list"]
        phase_ring = tuple(tuple(row) for row in options["phases"])
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
        for group in self._groups:
            group.add_extenders(extenders_by_group.get(group.id, []))

        self.sumo_outputs: list[SignalGroup] = list(self._groups)
        self._set_phase_ring(phase_ring)
        self._state: str = "Scan"

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
            str(self.current_main_phase) if self.current_main_phase else "",
            str(self.next_main_phase) if self.next_main_phase else "",
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
            OC_TO_SUMO_MAP.get(grp.signal_state, "r") for grp in self._groups
        )

    def tick(self) -> None:
        """Advance all signal groups and process phase transitions."""
        for grp in self._groups:
            grp.tick()
        self._update_states()

    def _update_states(self) -> None:
        """Manage round-robin phase selection and state flow."""
        if self._state == "Scan":
            self.next_main_phase = self._find_next_main_phase()
            if self.next_main_phase:
                self.next_main_phase.set_signalgroup_green_permissions(do_permit=True)

        # Clear green permission once minimum green step initiates
        for grp in self._groups:
            if grp.state == "Green_MinimumTime":
                grp.green_permission = False

        # Transition to Hold state once next phase has started
        if self.next_main_phase and self.next_main_phase.phase_has_started():
            self.current_main_phase = self.next_main_phase
            self.next_main_phase = None
            self._state = "Hold"
            if self._print_status:
                print(
                    f"{self._timer.seconds}s {self.id} "
                    f"STARTED: {self.current_main_phase}",
                )

        # Maintain permissions during Hold until minimum greens complete
        if self._state == "Hold" and self.current_main_phase:
            self.current_main_phase.set_signalgroup_green_permissions(do_permit=True)
            if self.current_main_phase.all_min_greens_have_ended():
                self._state = "Scan"
                if self._print_status:
                    print(
                        f"{self._timer.seconds}s {self.id} "
                        f"MIN TIMES ENDED: {self.current_main_phase}",
                    )

    def _find_next_main_phase(self) -> SimplePhase | None:
        """Find next phase with an active request using round-robin scan."""
        if self.current_main_phase in self.main_phases:
            idx = self.main_phases.index(self.current_main_phase)
            phase_order = self.main_phases[idx + 1 :] + self.main_phases[: idx + 1]
        else:
            phase_order = list(self.main_phases)

        return next((p for p in phase_order if p.phase_has_a_request()), None)

    def _set_conflict_groups(self, intergreen_matrix: list[list[float]]) -> None:
        """Assign conflicting signal groups based on the intergreen matrix."""
        for i, grp in enumerate(self._groups):
            conflicts = [
                self._groups[j]
                for j, delay in enumerate(intergreen_matrix[i])
                if delay > 0.0
            ]
            grp.add_conflict_groups(conflicts)

    def _set_phase_ring(self, phase_ring: tuple[tuple[int, ...], ...]) -> None:
        """Configure main phase ring matrix."""
        self.main_phases: list[SimplePhase] = []
        for idx, row in enumerate(phase_ring, start=1):
            phase_groups = [
                grp
                for grp, active in zip(self._groups, row, strict=True)
                if active == 1
            ]
            self.main_phases.append(SimplePhase(idx, phase_groups))

        self.current_main_phase: SimplePhase | None = None
        self.next_main_phase: SimplePhase | None = None

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
                    opts,
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
                    lambda: grp.green_started_at,
                )
            else:
                raise ValueError(
                    f"Unknown extender type {e_type} in controller {self.id}",
                )

            extenders.setdefault(group_id, []).append(extender)

        return extenders

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
