from typing import Any

from services.control_engine.src.signal_controller import (
    ControllerStatus,
    SignalController,
)
from services.control_engine.src.timer import Timer


class FixedTimeController(SignalController):
    """Very dumb fixed time signal controller.

    This is not a real production controller. It is here just for testing and
    demonstration purposes. It can be thought of as a Hello World for Open
    Controller.
    """

    def __init__(
        self,
        controller_id: str,
        timer: Timer,
        raw_options: dict[str, Any],
    ) -> None:
        super().__init__()

        self._id = controller_id
        self._timer = timer
        self._last_changed = timer.seconds

        self._raw_options = raw_options

        self._phases: list[tuple[str, float]] = []
        yellow_duration = float(raw_options["yellow_duration"])
        for phase in raw_options["phases"]:
            states = str(phase["signal_states"])
            duration = float(phase["duration"])
            # The actual state is added to the list of phases.
            self._phases.append((states, duration))

            # Yellow "intergreen" state follows the previous state.
            yellow_states = states.replace("g", "y")
            self._phases.append((yellow_states, yellow_duration))

        self._cur_phase_idx: int = 0

        self._step_count = 0

    @property
    def id(self) -> str:
        return self._id

    def tick(self) -> None:
        self._step_count += 1

        time_since_update = self._timer.seconds - self._last_changed

        # If enough time has passed, controller moves to the next phase.
        if time_since_update >= self._phases[self._cur_phase_idx][1]:
            self._cur_phase_idx = self._next_phase_idx()

    def reset(self) -> None:
        return self.reload()

    def reload(self) -> None:
        self.__init__(self._id, self._timer, self._raw_options)

    def save(self, filename: str) -> None:
        pass

    def all_red(self) -> None:
        raise NotImplementedError(
            "Fixed time controller doesn't implement all_red yet.",
        )

    @property
    def status(self) -> ControllerStatus:
        next_phase_idx = self._next_phase_idx()
        return ControllerStatus(
            self._step_count,
            self.signal_states,
            _sumo_states_to_oc(self._phases[next_phase_idx][0]),
        )

    @property
    def status_dict(self) -> dict[str, Any]:
        status = self.status

        return {
            "step_count": status.step_count,
            "current_phase": status.current_phase,
            "next_phase": status.next_phase,
        }

    @property
    def signal_states(self) -> str:
        return _sumo_states_to_oc(self.signal_states_sumo)

    @property
    def signal_states_sumo(self) -> str:
        return self._phases[self._cur_phase_idx][0]

    def _next_phase_idx(self) -> int:
        if not self._phases:
            raise ValueError("Cannot get next phase index because _phases is empty.")

        return (self._cur_phase_idx + 1) % len(self._phases)


def _sumo_states_to_oc(signal_states: str) -> str:
    mapping_table = str.maketrans({"r": "b", "g": "5", "y": "<"})
    return signal_states.translate(mapping_table)
