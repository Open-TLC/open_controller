import sys
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, TypedDict

from transitions.extensions import HierarchicalGraphMachine, HierarchicalMachine
from transitions.extensions.diagrams_graphviz import NestedGraph

from services.control_engine.src.configuration import ClockworkConf, read_command_line
from services.control_engine.src.extenders.extender import Extender
from services.control_engine.src.requesters.requester import Requester

from .timer import Timer

BLOCKING_STATES: set[str] = {"g", "0", "1", "4", "5", "<"}

MACHINE_STATE_TO_OC_MAP: dict[str, str] = {
    "Red_MinimumTime": "a",
    "Red_WaitRequestAndPermission": "b",
    "Red_EndingConflicts": "f",
    "Red_WaitIntergreen": "g",
    "AmberRed_MinimumTime": "0",
    "Green_MinimumTime": "1",
    "Green_Extending": "5",
    "Green_RemainGreen": "4",
    "Amber_MinimumTime": "<",
}


class SignalGroupConfig(TypedDict):
    """Configuration options for a signal group."""

    min_amber_red: float
    min_green: float
    max_green: float
    remain_green: bool
    min_amber: float
    min_red: float
    constant_request: bool


class SignalGroup:
    """Signal group used in group based control."""

    def __init__(
        self,
        timer: Timer,
        group_id: str,
        group_conf: SignalGroupConfig,
        intergreens: dict[str, float],
        # min_length: float,
        # max_length: float,
        # remain_green: bool,
    ) -> None:
        """Create new signal group.

        Args:
            timer: Timer object used by the controller.
            group_id: Unique ID of the signal group.
            group_conf: Configuration parameters for timing and behavior rules.
            intergreens: Dictionary of intergreen times by ending group ID.

        """
        self._id = group_id
        self._timer = timer
        self._intergreens = intergreens
        self.conflict_groups: list[SignalGroup] = []
        self._extenders: list[Extender] = []
        self._requesters: list[Requester] = []

        self._min_red_time = group_conf["min_red"]
        self._amber_red_time: float = group_conf["min_amber_red"]
        self._min_green_time = group_conf["min_green"]
        self._min_amber_time = group_conf["min_amber"]

        self._constant_request: bool = group_conf["constant_request"]
        self._max_green_time = group_conf["max_green"]
        self._remain_green = group_conf["remain_green"]

        self._signal_state: str = "a"
        self.green_permission: bool = False
        self.end_green_requested: bool = False

        self.red_started_at: float = 0.0
        self.amber_red_started_at: float = 0.0
        self.green_started_at: float = 0.0
        self.amber_started_at: float = 0.0

    def add_conflict_groups(self, groups: list["SignalGroup"]) -> None:
        """Add conflicting groups for the group."""
        self.conflict_groups.extend(groups)

    def add_extenders(self, extenders: list[Extender]) -> None:
        """Add extenders for the group."""
        self._extenders.extend(extenders)

    def add_requesters(self, requesters: list[Requester]) -> None:
        """Add requesters for the group."""
        self._requesters.extend(requesters)

    @property
    def id(self) -> str:
        """ID of the signal group."""
        return self._id

    @property
    def signal_state(self) -> str:
        """Groups state in OC format."""
        return self._signal_state

    def set_signal_state(self, sig_state: str):
        """Set group state in OC format."""
        self._signal_state = sig_state

    @property
    def is_blocking(self) -> bool:
        """Group is in state, that blocks conflict groups."""
        return self.signal_state in BLOCKING_STATES

    def tick(self) -> None:
        """Update signal group."""
        for req in self._requesters:
            req.tick()

        for ext in self._extenders:
            ext.tick()

            # if self._id == "group1": # Bedug
            Debug = True

        self.tick_vehicle_actuated()

    def tick_fixed_time(self):

        if self.signal_state == "a" and self._min_red_time_passed():
            self._amber_red_start_at()
            self.set_signal_state("0")

        elif self.signal_state == "0" and self._min_amber_red_time_passed():
            self._green_start_at()
            self.set_signal_state("1")

        elif self.signal_state == "1" and self._min_green_time_passed():
            self._amber_start_at()
            self.set_signal_state("<")

        elif self.signal_state == "<" and self._min_amber_time_passed():
            self._red_start_at()
            self.set_signal_state("a")

    def tick_vehicle_actuated(self):

        debug = True  # Debugging helper, set state and group you want to debug
        if debug:
            self._define_breakpoint()

        if self.signal_state == "a" and self._min_red_time_passed():
            self._amber_red_start_at()
            self.set_signal_state("b")

        elif self.signal_state == "b" and self.is_requesting:
            self.set_signal_state("c")

        elif self.signal_state == "c" and self.green_permission:
            self.set_signal_state("f")
            self.end_conflict_greens()

        elif self.signal_state == "f" and not (self.conflict_group_blocking()):
            self.set_signal_state("g")

        elif self.signal_state == "g" and self.intergreens_passed():
            self.set_signal_state("0")

        elif self.signal_state == "0" and self._min_amber_red_time_passed():
            self._green_start_at()
            self.set_signal_state("1")

        elif self.signal_state == "1" and self._min_green_time_passed():
            self.set_signal_state("5")
            self.end_green_requested = False

        elif self.signal_state == "5" and not (self.is_extending):
            self.set_signal_state("4")

        elif self.signal_state == "4" and self.end_green_requested:
            self._amber_start_at()
            self.set_signal_state("<")

        elif self.signal_state == "<" and self._min_amber_time_passed():
            self._red_start_at()
            self.set_signal_state("a")

    def _define_breakpoint(self):
        if (
            (self.signal_state == "g")
            and (self._id == "group3")
            and (self._timer.seconds >= 21.0)
        ):
            breakpoint = True  # Set your breakpoint here
        else:
            breakpoint = False

    def _red_start_at(self) -> None:
        self.red_started_at = self._timer.seconds

    def _amber_red_start_at(self) -> None:
        self.amber_red_started_at = self._timer.seconds

    def _green_start_at(self) -> None:
        self.green_started_at = self._timer.seconds

    def _amber_start_at(self) -> None:
        self.amber_started_at = self._timer.seconds

    def _min_red_time_passed(self) -> bool:
        ret = self.red_started_at + self._min_red_time < self._timer.seconds
        return ret

    def _min_amber_red_time_passed(self) -> bool:
        ret = self.amber_red_started_at + self._amber_red_time < self._timer.seconds
        return ret

    def _min_green_time_passed(self) -> bool:
        return self.green_started_at + self._min_green_time < self._timer.seconds

    def _min_amber_time_passed(self) -> bool:
        return self.amber_started_at + self._min_amber_time < self._timer.seconds

    @property
    def is_extending(self) -> bool:
        """Group is extending current green."""
        return any(ext.is_extending for ext in self._extenders)

    @property
    def is_requesting(self) -> bool:
        """Group is requesting green."""
        return (
            any(req.is_requesting for req in self._requesters) or self._constant_request
        )

    def conflict_group_blocking(self) -> bool:
        """Check if any conflicting group is blocking."""
        for grp in self.conflict_groups:
            if grp.is_blocking:
                pass
        return any(grp.is_blocking for grp in self.conflict_groups)

    def end_conflict_greens(self) -> None:
        """Request all conflicting groups to end their greens."""
        for group in self.conflict_groups:
            if self.signal_state in ["f"]:
                print(
                    "group: ",
                    self._id,
                    " state: ",
                    self.signal_state,
                    " end group: ",
                    group._id,
                )
                group.end_green_requested = True

    def intergreens_passed(self) -> bool:
        """Check if all conflict group intergreen times have passed."""
        return all(
            self._timer.seconds - grp.amber_started_at
            > self._intergreens[grp.id] - self._amber_red_time
            for grp in self.conflict_groups
        )

    def give_green_permission(self) -> None:
        """Give green permission to group and take conflict green permissions away."""
        for grp in self.conflict_groups:
            grp.green_permission = False
        self.green_permission = True

    def _max_green_time_passed(self) -> bool:
        """Group has extended past its maximum allowed time."""
        return self.green_started_at + self._max_green_time < self._timer.seconds

    def _end_green_requested(self) -> bool:
        return self.end_green_requested

    def _end_green_off(self) -> None:
        self.end_green_requested = False

    def _start_waiting_req_and_perm(self) -> None:
        pass
