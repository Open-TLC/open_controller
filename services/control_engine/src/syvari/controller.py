from ..detector import Detector
from ..signal_controller import SignalController
from .configuration import SyvariControllerConfiguration
from .cycle_timer import CycleTimer
from .signal_group import GroupState, SignalGroup, group_state_to_string


class SyvariController(SignalController):
    """
    Implementation of SignalController base class. Follows the control logic of SYVARI.
    """

    def __init__(self, conf: SyvariControllerConfiguration, timer: CycleTimer) -> None:
        """
        Args:
            conf: Configuration used for the controller instance. This must be initialized before creating controller.
            timer: System timer used for the entire scenario.
        """

        # Save configuration and timer objects
        self._name = conf.name
        self._sumo_name = conf.sumo_name
        self._timer: CycleTimer = timer

        # List of signal group names that determines the output state string format
        self._state_format = conf.state_format

        if len(conf.group_confs) == 0:
            raise ValueError("Controller doesn't have signal groups configured.")

        # Create signal groups
        self._signal_groups: dict[str, SignalGroup] = {}
        for group_conf in conf.group_confs:
            group = SignalGroup(timer, group_conf)
            self._signal_groups[group.name] = group

        # Matrix of active group names per phase
        self._phases = conf.phases

        # Current phase index.
        self._cur_phase_idx: int = 0

        # Signal groups in the first phase start their greens.
        for group_name in self._phases[0]:
            self._signal_groups[group_name].start_green()

    @property
    def status(self) -> str:
        """
        Open Controller signal controller status string.
        """
        # TODO: Implement the method
        raise NotImplementedError("SyvariController.status not implemented")

    @property
    def name(self) -> str:
        return self._name

    @property
    def sumo_name(self) -> str:
        return self._sumo_name

    @property
    def e1_detectors(self) -> list[Detector]:
        detectors: list[Detector] = []

        for group in self._signal_groups.values():
            detectors.extend(group.e1_detectors)

        return detectors

    @property
    def e3_detectors(self) -> list[Detector]:
        detectors: list[Detector] = []

        for group in self._signal_groups.values():
            detectors.extend(group.e3_detectors)

        return detectors

    def tick(self) -> str:
        """
        Advance the controller by a single time step. It reads the detector
        data, decides the new signal states and returns them as a string.

        Returns:
            states: Signal states as a SUMO string. This can be passed to the traffic controller.
        """

        # Update all signal groups
        for group in self._signal_groups.values():
            group.tick()

        # If current groups are amber (i.e. they are just starting to turn green)
        # controller can't advance.
        if self._current_groups_in_amber():
            return self._get_group_states()

        # If current phase has groups with guaranteed green left, controller can't advance.
        if self._current_groups_in_guaranteed_green():
            return self._get_group_states()

        # If another group in the future has a priority request and none of the current
        # groups are priority extending, the controller advances.
        if (
            self._future_priority_request_exists()
            and not self._current_groups_priority_extending()
        ):
            _ = self._move_to_next_phase()
            return self._get_group_states()

        # If current phase still has groups in active green, the existing state is returned.
        if self._current_groups_in_active_green():
            return self._get_group_states()

        # If all groups in the current phase have ended their active green, controller tries to move to the next phase.
        _ = self._move_to_next_phase()

        return self._get_group_states()

    def _get_group_states(self) -> str:
        states: str = ""
        for group_name in self._state_format:
            group = self._signal_groups[group_name]
            group_state = group_state_to_string(group.state)
            states = states + group_state

        return states

    def _move_to_next_phase(self) -> bool:
        """Move to the next phase if possible.
        Controller tries to advance its state, but fails if previous groups are still active.

        Returns:
            Whether phase changed.
        """
        for group in self._phases[self._cur_phase_idx]:
            self._signal_groups[group].end_green()

        # If a group is still yellow, controller can't advance.
        if not self._current_groups_red():
            return False

        # Controller moves to the next phase.
        self._cur_phase_idx = self._get_next_phase_idx()

        # Signal groups in the new phase start their greens.
        for group in self._phases[self._cur_phase_idx]:
            self._signal_groups[group].start_green()

        return True

    def _get_next_phase_idx(self) -> int:
        """Determines the index of the next scheduled phase in the sequence loop.

        Returns:
            The index integer of the upcoming phase, handling boundary wrap-arounds.
        """
        if self._cur_phase_idx < len(self._phases) - 1:
            return self._cur_phase_idx + 1
        return 0

    def _current_groups_in_active_green(self) -> bool:
        """Checks if any group in the current phase is currently running an active green.

        Returns:
            True if at least one group is in GroupState.ACTIVE_GREEN, False otherwise.
        """
        return any(
            self._signal_groups[group].state == GroupState.ACTIVE_GREEN
            for group in self._phases[self._cur_phase_idx]
        )

    def _current_groups_in_amber(self) -> bool:
        """Check if any group in the current phase is currently amber.

        Returns:
            True if at least one group is in GroupState.AMBER, False otherwise.
        """
        return any(
            self._signal_groups[group].state == GroupState.AMBER
            for group in self._phases[self._cur_phase_idx]
        )

    def _current_groups_red(self) -> bool:
        """Checks if all groups in the current phase have transitioned completely to red.

        Used to ensure a completely safe clearance interval before launching conflicting greens.

        Returns:
            True if every group in the current phase is GroupState.RED, False otherwise.
        """
        return all(
            self._signal_groups[group].state == GroupState.RED
            for group in self._phases[self._cur_phase_idx]
        )

    def _current_groups_in_guaranteed_green(self) -> bool:
        """Checks if any group in the current phase is protected by guaranteed minimum green requirements.

        Returns:
            True if a current group is locked into its minimum green phase time constraint.
        """
        return any(
            self._signal_groups[group_name].has_guaranteed_green_left
            for group_name in self._phases[self._cur_phase_idx]
        )

    def _current_groups_priority_extending(self) -> bool:
        """Checks if any group in the current phase is priority extending.

        Returns:
            True if a current group has a priority extension.
        """
        return any(
            self._signal_groups[group_name].is_priority_extending
            for group_name in self._phases[self._cur_phase_idx]
        )

    def _future_priority_request_exists(self) -> bool:
        phase_count = len(self._phases)

        for offset in range(1, phase_count):
            idx = (self._cur_phase_idx + offset) % phase_count

            if any(
                self._signal_groups[g].is_priority_requesting for g in self._phases[idx]
            ):
                return True

        return False


import unittest


class TestSyvariConfiguration(unittest.TestCase):
    def test_create_controller(self):
        timer_prm = {
            "timer_mode": "fixed",
            "time_step": 0.1,
            "real_time_multiplier": 1,
        }
        cycle_length = 60
        timer = CycleTimer(timer_prm, cycle_length)

        controller_params = {  # Very minimal SYVARI controller configuration
            "name": "example_controller",
            "sumo_name": "controller_1",
            "signal_groups": {
                "group_1": {
                    "name": "group_1",
                    "sync_start": 0,
                    "sync_end": 30,
                    "min_green": 5,
                    "min_guaranteed": 15,
                },
                "group_2": {
                    "name": "group_2",
                    "sync_start": 30,
                    "sync_end": 59,
                    "min_green": 5,
                    "min_guaranteed": 15,
                },
            },
            "detectors": {
                "detector_1": {
                    "type": "e3detector",
                    "sumo_id": "abc",
                    "group": "group_1",
                },
                "detector_2": {
                    "type": "request",
                    "sumo_id": "def",
                    "request_groups": ["group_2"],
                },
            },
            "group_list": ["group_1", "group_2"],
            "phases": [
                [1, 0],
                [0, 1],
            ],
            "intergreens": [
                [0, 3],
                [3, 0],
            ],
        }

        controller_conf = SyvariControllerConfiguration(
            controller_params["name"], controller_params
        )
        controller = SyvariController(controller_conf, timer)

        self.assertNotEqual(controller, None)


if __name__ == "__main__":
    unittest.main()
