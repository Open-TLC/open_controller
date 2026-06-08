from enum import Enum

from src.detector import Detector, e3Detector

from services.control_engine.src.syvari.configuration import SyvariGroupConfiguration

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
            sync_start: Target green start time for the group (point in cycle).
            sync_end: Target green end time for the group (point in cycle).
            min_green: Minimum green phase duration (seconds).
            min_guaranteed: Minimum time that the group is guaranteed to have.
                            Doesn't have to be used fully. (Takuumaksimi) (seconds).
            priority_max: Maximum extension duration allowed when processing
                            public transit priority requests (Etuusmaksimi) (seconds).

        Raises:
            ValueError
        """
        self._timer = timer
        self._name = conf.name
        self._conflict_groups = conf.conflict_groups

        if (
            max(conf.sync_start, conf.sync_end) >= timer.cycle_length
            or min(conf.sync_start, conf.sync_end) < 0
        ):
            raise ValueError(
                "Invalid params: sync_start and sync_end must be between 0 and cycle_length."
            )
        self._sync_start = conf.sync_start
        self._sync_end = conf.sync_end

        target_phase_duration = (conf.sync_end - conf.sync_start) % timer.cycle_length

        if conf.min_green > target_phase_duration:
            raise ValueError(
                f"Invalid params: min_green ({conf.min_green}s) cannot be longer than "
                f"the target phase window ({target_phase_duration}s)."
            )

        if conf.min_guaranteed < conf.min_green:
            raise ValueError(
                f"Invalid params: min_guaranteed ({conf.min_guaranteed}s) must be greater than "
                f"or equal to min_green ({conf.min_green}s)."
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

        # Keeps track of the last time at which an extension pulse was received.
        # This will be set to None when group ends its active green.
        self._last_extended: float | None = 0

        self._cur_state = GroupState.RED
        self._is_requesting: bool = False
        # TODO: Implement a way to accept priority requests
        self._is_priority_requesting: bool = False

        # TODO: Populate detector lists
        self._e3_detectors: list[e3Detector] = []
        self._loop_detectors: list[Detector] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> GroupState:
        return self._cur_state

    @property
    def is_requesting(self) -> bool:
        return self._is_requesting

    def tick(self) -> None:
        """
        tick advances the group by one step. This updates the
        groups state based on the latest detector readings.
        """
        if self._cur_state == GroupState.RED:
            self._is_requesting = self._has_vehicles()

        # Only active green needs to handle extension logic
        if self._cur_state != GroupState.ACTIVE_GREEN:
            return

        # Extender timer must be updated before getting new state
        self._update_extenders()

        self._cur_state = self._get_new_state()

    def start_green(self) -> None:
        """
        Puts the group to active green. The group will be responsible
        for returning to passive green after the conditions are met.
        """
        self._cur_state = GroupState.ACTIVE_GREEN
        self._green_start_time = self._timer.cycle_phase

        self._is_requesting = False

    def _get_new_state(self) -> GroupState:
        # Only active green will be changed depending on traffic situation.
        if self._cur_state != GroupState.ACTIVE_GREEN or self._green_start_time is None:
            return self._cur_state

        time_since_start = (
            self._timer.cycle_phase - self._green_start_time
        ) % self._timer.cycle_length

        # If minimum green hasn't been used, group remains in the same state.
        if time_since_start < self._min_green:
            return self._cur_state

        max_sync_duration = (
            self._sync_end - self._green_start_time
        ) % self._timer.cycle_length

        # If group has exceeded its sync_end, it must end its active green.
        if time_since_start >= max_sync_duration:
            return GroupState.PASSIVE_GREEN

        min_sync_duration = (
            self._min_end - self._green_start_time
        ) % self._timer.cycle_length

        # If group doesn't want to extend and has passed min_end, it can end its active green.
        if not self._is_extending() and time_since_start >= min_sync_duration:
            return GroupState.PASSIVE_GREEN

        # Otherwise the group stays active
        return GroupState.ACTIVE_GREEN

    def _update_extenders(self) -> None:
        """
        Updates the extension timer based on state and detector readings.
        """
        if self._cur_state != GroupState.ACTIVE_GREEN:
            self._last_extended = None
            return

        if self._has_vehicles():
            self._last_extended = self._timer.cycle_phase

    def _is_extending(self) -> bool:
        """
        Checks if the group is currently trying to extend its active green.
        """
        if self._cur_state != GroupState.ACTIVE_GREEN:
            return False

        # If we haven't seen a single vehicle yet this entire green phase
        if self._last_extended is None:
            return False

        # Calculate exactly how many seconds have flown by since the last vehicle reset
        time_since_last_vehicle = (
            self._timer.cycle_phase - self._last_extended
        ) % self._timer.cycle_length

        # If the gap between vehicles is smaller than our threshold, keep extending
        return time_since_last_vehicle < EXTENSION_LENGTH

    def _has_vehicles(self) -> bool:
        # Gather e3 detector readings
        veh_count: int = 0
        for det in self._e3_detectors:
            veh_count += det.veh_count()

        has_loop_activations: bool = False
        # Check if any request detectors have requests
        for det in self._loop_detectors:
            if det.loop_on:
                has_loop_activations = True
                break

        return veh_count > 0 or has_loop_activations
