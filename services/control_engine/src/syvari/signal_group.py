from enum import Enum
from typing import Sequence

from ..detector import Detector, e3Detector
from .configuration import SyvariGroupConfiguration
from .cycle_timer import CycleTimer


class GroupState(Enum):
    RED = "r"
    AMBER = "u"
    ACTIVE_GREEN = "G"
    PASSIVE_GREEN = "g"
    YELLOW = "y"


def group_state_to_string(state: GroupState) -> str:
    """
    group_state_to_string maps a state enum to Open Controller state character.

    Args:
        state: Group state to convert.

    Returns:
        state string: The character representation of the state.
    """
    return state.value


# TODO: Read extension from configuration
EXTENSION_LENGTH: float = 3


class SignalGroup:
    def __init__(
        self,
        timer: CycleTimer,
        conf: SyvariGroupConfiguration,
    ) -> None:
        """
        Args:
            timer: Cycle timer used by the controller.
            conf: Signal group configuration.

        Raises:
            ValueError
        """
        self._timer = timer
        self._name = conf.name
        self._yellow = conf.yellow

        if (
            max(conf.sync_start, conf.sync_end) >= timer.cycle_length
            or min(conf.sync_start, conf.sync_end) < 0
        ):
            raise ValueError(
                "Invalid params: sync_start and sync_end must be between 0 and cycle_length."
            )
        self._sync_start = conf.sync_start
        # Group has to end its green enough in advance to have the time for a yellow
        self._sync_end = conf.sync_end - self._yellow

        target_phase_duration = (conf.sync_end - conf.sync_start) % timer.cycle_length

        if conf.min_green > target_phase_duration:
            raise ValueError(
                f"Invalid params: min_green ({conf.min_green}s) cannot be longer than "
                f"the target phase window ({target_phase_duration}s)."
            )

        if conf.min_guaranteed < conf.min_green:
            raise ValueError(
                f"Invalid params: min_guaranteed ({conf.min_guaranteed}s) can't be "
                f"smaller than min_green ({conf.min_green}s)."
            )
        self._min_green = conf.min_green
        self._min_guaranteed = conf.min_guaranteed

        # min_end represents the earliest point at which the group can end its green.
        # This makes sure that the cycle doesn't get too much ahead of itself.
        self._min_end = conf.sync_start + conf.min_green

        # If no priority maximum is provided, it defaults to the standard synced window length
        if conf.priority_max is None:
            self._priority_max = target_phase_duration
        else:
            self._priority_max = conf.priority_max

        # Keeps track of the current phases start time
        self._green_start_time: float | None = None

        # Keeps track of the yellow start.
        # This is used to transition from yellow to red.
        self._yellow_start_time: float | None = None

        # Keeps track of the last time at which an extension pulse was received.
        # This will be set to None when group ends its active green.
        self._last_extended: float | None = None
        self._last_priority_extended: float | None = None

        self._cur_state = GroupState.RED
        self._is_requesting: bool = False
        self._is_priority_requesting: bool = False

        self._e3_detectors: list[e3Detector] = []
        self._loop_detectors: list[Detector] = []

        for det_name in conf.detector_confs:
            det_type: str = conf.detector_confs[det_name]["type"]
            if det_type == "request":
                det = Detector(self._timer, det_name, conf.detector_confs[det_name])
                self._loop_detectors.append(det)
            elif det_type == "e3detector":
                det = e3Detector(self._timer, det_name, conf.detector_confs[det_name])
                self._e3_detectors.append(det)
            else:
                raise TypeError(f"Unknown detector type for {det_name}: {det_type}")

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> GroupState:
        return self._cur_state

    @property
    def is_requesting(self) -> bool:
        return self._is_requesting

    @property
    def is_priority_requesting(self) -> bool:
        return self._is_priority_requesting

    @property
    def is_priority_extending(self) -> bool:
        return self._is_priority_extending()

    @property
    def has_guaranteed_green_left(self) -> bool:
        if self._green_start_time is None:
            return False

        time_since_green = (
            self._timer.cycle_phase - self._green_start_time
        ) % self._timer.cycle_length

        return time_since_green < self._min_guaranteed

    @property
    def e1_detectors(self) -> Sequence[Detector]:
        return self._loop_detectors

    @property
    def e3_detectors(self) -> Sequence[Detector]:
        return self._e3_detectors

    def tick(self) -> None:
        """
        tick advances the group by one step. This updates the
        groups state based on the latest detector readings.
        """
        # This will update the extension logic if necessary.
        self._update_extension()

        # If group is in yellow and has been yellow for long enough, it will transition to red.
        if self._cur_state == GroupState.YELLOW:
            self._tick_on_yellow()

        # If group is in red, it updates its request states.
        elif self._cur_state == GroupState.RED:
            self._tick_on_red()

        # If group is in passive green, it will do nothing.
        elif self._cur_state == GroupState.PASSIVE_GREEN:
            pass

        # If group is in green, it will check, whether to
        # extend its active green or transition to passive.
        elif self._cur_state == GroupState.ACTIVE_GREEN:
            self._tick_on_green()

        else:
            raise ValueError("Unknown group state: ", self._cur_state)

    def start_green(self) -> None:
        """
        Puts the group to active green. The group will be responsible
        for returning to passive green after the conditions are met.
        """
        # If group is already in active green, it will remain like this
        if self._cur_state == GroupState.ACTIVE_GREEN:
            return
        self._cur_state = GroupState.ACTIVE_GREEN
        self._green_start_time = self._timer.cycle_phase
        self._last_extended = None
        self._last_priority_extended = None

        self._is_requesting = False
        self._is_priority_requesting = False

    def end_green(self) -> None:
        """
        Puts the group to yellow. The group will switch to red itself.
        """
        if self._cur_state in (GroupState.PASSIVE_GREEN, GroupState.ACTIVE_GREEN):
            self._cur_state = GroupState.YELLOW
            self._yellow_start_time = self._timer.cycle_phase
            self._green_start_time = None

    def _tick_on_red(self) -> None:
        """Update group while on red.
        This will update group's request status depending on detectors.
        """
        self._is_requesting = self._is_requesting or self._has_vehicles()
        self._is_priority_requesting = (
            self._is_priority_requesting or self._has_priority_vehicles()
        )

    def _tick_on_yellow(self) -> None:
        """Update group while yellow.
        This will check if group should turn red and update it's state according
        to it.
        """
        if self._yellow_start_time is None:
            self._yellow_start_time = self._timer.cycle_phase

        time_since_yellow = (
            self._timer.cycle_phase - self._yellow_start_time
        ) % self._timer.cycle_length

        if time_since_yellow >= self._yellow:
            self._cur_state = GroupState.RED
            self._yellow_start_time = None

    def _tick_on_green(self) -> None:
        # If green start time hasn't been recorded, it is set to current cycle phase.
        if self._green_start_time is None:
            self._green_start_time = self._timer.cycle_phase

        time_since_start = (
            self._timer.cycle_phase - self._green_start_time
        ) % self._timer.cycle_length

        # If minimum green hasn't been used, group remains in active green.
        if time_since_start < self._min_green:
            return

        # If group is priority extending and hasn't used the
        # priority max time, it will continue it's extension.
        if self._is_priority_extending() and time_since_start < self._priority_max:
            return

        # This could be calculated once every green,
        # but is done here to simplify the logic.
        max_sync_duration = (
            self._sync_end - self._green_start_time
        ) % self._timer.cycle_length

        # If group has exceeded its sync_end, it must end its active green.
        if time_since_start >= max_sync_duration:
            self._cur_state = GroupState.PASSIVE_GREEN
            return

        # This could be calculated once every green,
        # but is done here to simplify the logic.
        min_sync_duration = (
            self._min_end - self._green_start_time
        ) % self._timer.cycle_length

        # If group doesn't want to extend and has passed
        # min_end, it can end its active green.
        if not self._is_extending() and time_since_start >= min_sync_duration:
            self._cur_state = GroupState.PASSIVE_GREEN
            return

    def _update_extension(self) -> None:
        """
        Updates the extension timer based on state and detector readings.
        """
        if self._cur_state != GroupState.ACTIVE_GREEN:
            self._last_extended = None
            self._last_priority_extended = None
            return

        # Update regular extension timer.
        if self._has_vehicles():
            self._last_extended = self._timer.cycle_phase

        # Update priority extension timer.
        if self._has_priority_vehicles():
            self._last_priority_extended = self._timer.cycle_phase

    def _is_extending(self) -> bool:
        """Check if the group is currently trying to extend its active green."""
        if self._cur_state != GroupState.ACTIVE_GREEN or self._last_extended is None:
            return False

        # Calculate exactly how many seconds have flown by since the last vehicle.
        time_since_last_vehicle = (
            self._timer.cycle_phase - self._last_extended
        ) % self._timer.cycle_length

        # If the gap between vehicles is smaller than our threshold, keep extending.
        return time_since_last_vehicle < EXTENSION_LENGTH

    def _is_priority_extending(self) -> bool:
        """Check if the group is currently trying to priority extend its active green."""
        if self._last_priority_extended is None:
            return False

        # Calculate exactly how many seconds have
        # flown by since the last priority vehicle
        time_since_last_priority_vehicle = (
            self._timer.cycle_phase - self._last_priority_extended
        ) % self._timer.cycle_length

        # If the gap between priority vehicles is
        # smaller than our threshold, keep extending
        return time_since_last_priority_vehicle < EXTENSION_LENGTH

    def _has_vehicles(self) -> bool:
        veh_count = sum(det.veh_count() for det in self._e3_detectors)

        # Evaluate if any short loop request channels are closed/on
        has_loop_activations = any(det.loop_on for det in self._loop_detectors)

        return veh_count > 0 or has_loop_activations

    def _has_priority_vehicles(self) -> bool:
        veh_count = sum(det.veh_count() for det in self._e3_detectors)

        # Currently e3 detectors count transit vehicles as 100 vehicles each.
        # TODO: Fix detector to return true/false if detects priority vehicles.
        return veh_count >= 100
