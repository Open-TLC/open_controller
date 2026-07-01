from typing import Any

import numpy as np

from services.control_engine.src.detectors.area_detector import AreaDetector
from services.control_engine.src.detectors.sumo_e2_detector import E2AreaDetector
from services.control_engine.src.detectors.sumo_e3_detector import E3AreaDetector
from services.control_engine.src.signal_controller import (
    ControllerStatus,
    SignalController,
)

from .configuration import ControllerConf
from .rl_util import get_observation, load_model
from .trafficenv import SafetyController


class BumblebeeController(SignalController):
    """Reinforcement learning signal controller."""

    def __init__(
        self,
        conf: ControllerConf,
        algorithm: str,
        filename: str,
        step_length: float,
    ) -> None:
        """Initialize Bumblebee controller.

        Args:
            conf: Controller configuration for the controller.
            algorithm: Algorithm used to train the
                model (currently supported: ppo and dqn).
            filename: Path to the trained model file.
            step_length: Time step between controller ticks in seconds.

        """
        self._model = load_model(algorithm, filename)

        self._conf = conf
        self._step_length = step_length

        # Intergreen matrix.
        intergreens = np.array(conf.intergreens)

        # Safety controller for handling conflicting phases and intergreens.
        self._safety_controller = SafetyController(
            intergreens,
            conf.group_outputs,
            step_length,
        )

        self._detectors: list[AreaDetector] = []
        for detector_conf in conf.detector_confs:
            detector: AreaDetector
            det_type: str = detector_conf.type
            det_id: str = detector_conf.id
            if det_type == "e2_detector":
                detector = E2AreaDetector(det_id)
            elif det_type == "e3_detector":
                detector = E3AreaDetector(det_id)
            else:
                raise ValueError(
                    f"Unknown detector type for detector {det_id}: {det_type}",
                )
            self._detectors.append(detector)

        self._cur_phase_idx: int = 0
        self._step_count: int = 0

        self._sumo_states: str = ""

    def tick(self) -> None:
        """Advance the controller by one time step."""
        obs = get_observation(
            self._cur_phase_idx,
            len(self._detectors),
            self._detectors,
        )
        action, _ = self._model.predict(obs)
        self._cur_phase_idx = int(action.item())

        self._sumo_states = self._safety_controller.step(self._cur_phase_idx)

        self._step_count += 1

    def reset(self) -> None:
        """Reset controller to default state.

        As BumblebeeController can't be modified during running,
        this is the same as reloading it from configuration.
        """
        return self.reload()

    def reload(self) -> None:
        """Reload controller from configuration."""
        intergreens = np.array(self._conf.intergreens)
        self._safety_controller = SafetyController(
            intergreens,
            self._conf.group_outputs,
            self._step_length,
        )

        self._cur_phase_idx: int = 0
        self._step_count: int = 0

    def save(self, filename: str) -> None:
        """Save controller configuration.

        As BumblebeeController can't be modified during running,
        doesn't do anything. It is still required to implement
        the abstract SignalController class.
        """
        pass

    def all_red(self) -> None:
        """Force safety controller to red gracefully."""
        raise NotImplementedError

    @property
    def status(self) -> ControllerStatus:
        """Controllers internal status."""
        return ControllerStatus(
            self._step_count,
            self._sumo_states,
            "This will be decided on the next tick",
        )

    @property
    def status_dict(self) -> dict[str, Any]:
        """Controllers internal status as a dictionary."""
        status = self.status
        return {
            "step_count": status.step_count,
            "current_phase": status.current_phase,
            "next_phase": status.next_phase,
        }

    @property
    def signal_states(self) -> str:
        """Signal states in Open Controller format."""
        raise NotImplementedError

    @property
    def signal_states_sumo(self) -> str:
        """Signal states in SUMO format."""
        return self._sumo_states
