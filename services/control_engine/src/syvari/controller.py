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

        if len(conf.group_confs) == 0:
            raise ValueError("Controller doesn't have signal groups configured.")

        # Create signal groups
        self._signal_groups: dict[str, SignalGroup] = {}
        for group_conf in conf.group_confs:
            group = SignalGroup(timer, group_conf)
            self._signal_groups[group.name] = group

        # Matrix of active group names per phase
        self._phases = conf.phases

        # Current phase index
        self._cur_phase_idx: int = 0

    @property
    def status(self) -> str:
        """
        Open Controller signal controller status string.
        """
        # TODO: Implement the method
        raise Exception("SyvariController.status not implemented")

    @property
    def name(self) -> str:
        return self._name

    @property
    def sumo_name(self) -> str:
        return self._sumo_name

    def tick(self) -> str:
        """
        tick advances the controller by a single time step. It reads the detector
        data, decides the new signal states and returns them as a string.

        Returns:
            states: Signal states as a SUMO string. This can be passed to the traffic controller.
        """

        # Update all signal groups
        for group in self._signal_groups.values():
            group.tick()

        # If current phase still has groups in active green, the existing state is returned.
        if self._current_groups_in_active_green():
            return self._get_group_states()

        # If all groups in the current phase have ended their active green, controller moves to the next phase.

        # Move to the next phase or loop back to the first
        if self._cur_phase_idx < len(self._phases) - 1:
            self._cur_phase_idx += 1
        else:
            self._cur_phase_idx = 0

        for group in self._phases[self._cur_phase_idx]:
            self._signal_groups[group].start_green()

        return self._get_group_states()

    def _get_group_states(self) -> str:
        states: str = ""
        for group in self._signal_groups.values():
            states = states + group_state_to_string(group.state)

        return states

    def _current_groups_in_active_green(self) -> bool:
        """
        Checks if any group in the current phase is in active green.

        Returns:
            If any group in the current phase is in active green.
        """

        current_phase_active = False

        for group in self._phases[self._cur_phase_idx]:
            if self._signal_groups[group].state == GroupState.ACTIVE_GREEN:
                current_phase_active = True
                break

        return current_phase_active


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

        controller_conf = SyvariControllerConfiguration(controller_params)
        controller = SyvariController(controller_conf, timer)

        self.assertNotEqual(controller, None)


if __name__ == "__main__":
    unittest.main()
