import numpy as np

from services.control_engine.src.detectors.area_detector import AreaDetector
from services.control_engine.src.detectors.sumo_e2_detector import E2AreaDetector
from services.control_engine.src.detectors.sumo_e3_detector import E3AreaDetector

from .configuration import BumblebeeControllerConf
from .rl_util import get_observation, load_model
from .trafficenv import SafetyController


class BumblebeeController:
    """Reinforcement learning signal controller."""

    def __init__(self, conf: BumblebeeControllerConf) -> None:
        self._model = load_model(conf.algorithm, conf.model_path)

        # Length of the simulated step in seconds.
        step_length = conf.step_length

        # Intergreen matrix.
        intergreens = np.array(conf.intergreens)

        # Safety controller for handling conflicting phases and intergreens.
        self._safety_controller = SafetyController(intergreens, step_length)

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
                    f"Unknown detector type for detector {det_id}: {det_type}"
                )
            self._detectors.append(detector)

        self._cur_phase_idx: int = 0

    def tick(self) -> str:
        """Advance the controller by one time step.

        Returns:
            New states for signal groups in the SUMO format."""

        obs = get_observation(
            self._cur_phase_idx, len(self._detectors), self._detectors
        )
        action, _ = self._model.predict(obs)
        self._cur_phase_idx = int(action.item())

        return self._safety_controller.step(self._cur_phase_idx)
