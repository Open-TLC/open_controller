from typing import Any

import numpy as np

from services.control_engine.src.detectors.area_detector import (
    AreaDetector,
    TransitAreaDetector,
)
from services.control_engine.src.geometry.movements import (
    LanePressureConfig,
)
from services.control_engine.src.signal_controller import (
    ControllerStatus,
    SignalController,
)
from services.control_engine.src.timer import Timer

from .configuration import BumblebeeControllerConf
from .frap_inference_network import load_model
from .rl_util import build_agent_pressure_configs, get_observation
from .trafficenv import SafetyController


class BumblebeeController(SignalController):
    """Reinforcement learning signal controller."""

    def __init__(
        self,
        conf: BumblebeeControllerConf,
        all_detectors: dict[str, AreaDetector],
        timer: Timer,
    ) -> None:
        """Initialize Bumblebee controller.

        Args:
            conf: Controller configuration for the controller.
            all_detectors: Detectors by ID.
            timer: Timer to be used for control.

        """
        self._conf = conf
        self._timer = timer

        # Safety controller for handling conflicting phases and intergreens.
        self._safety_controller = SafetyController(
            conf.intergreens,
            conf.geometry,
            timer,
        )

        # Load trained PyTorch model.
        self._model = load_model(
            model_file=conf.model_file,
            num_phases=self._safety_controller.phase_count,
            hidden_dim=getattr(conf, "hidden_dim", 32),
            embed_dim=getattr(conf, "embed_dim", 16),
        )

        detectors, pressure_configs = build_agent_pressure_configs(conf, all_detectors)

        self._detectors: list[AreaDetector] = detectors
        self._lane_pressure_configs: list[LanePressureConfig] = pressure_configs

        # Filter and save transit detectors.
        self._transit_detectors: list[TransitAreaDetector] = [
            det for det in detectors if isinstance(det, TransitAreaDetector)
        ]

        self._cur_phase_idx: int = 0
        self._phase_start_time: float = self._timer.seconds
        self._step_count: int = 0
        self._sumo_states: str = ""
        self._locked: bool = False  # Used to lock controller state in failure

    def tick(self) -> None:
        """Advance the controller by one time step."""
        for detector in self._detectors:
            detector.tick()

        # Controller doesn't advance to new phases if it is locked.
        # This is done to lock it to red in case of a major failure.
        if not self._locked:
            cur_phase_idx = self._cur_phase_idx
            phase_count = self._safety_controller.phase_count
            pressure_configs = self._lane_pressure_configs

            elapsed_time = self._timer.seconds - self._phase_start_time

            transit_detections: np.ndarray = np.array(
                [det.vehicle_count for det in self._transit_detectors],
            )
            phase_wise_transit_detections = (
                self._safety_controller.get_phase_wise_transit_detections(
                    transit_detections,
                )
            )

            phase_active_lanes = self._safety_controller.phases_lane

            obs = get_observation(
                cur_phase_idx,
                elapsed_time,
                phase_count,
                pressure_configs,
                phase_wise_transit_detections,
                phase_active_lanes,
            )

            next_phase_idx = self._model.predict(obs)

            if next_phase_idx != cur_phase_idx:
                self._phase_start_time = self._timer.seconds
                self._cur_phase_idx = next_phase_idx

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
        self._safety_controller = SafetyController(
            self._conf.intergreens,
            self._conf.geometry,
            self._timer,
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
        self._cur_phase_idx = 0  # 0 is always the index of all red phase.
        self._locked = True  # Lock the controller to the current phase.

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
        mapping_table = str.maketrans({"r": "b", "g": "5", "y": "<"})

        return self._sumo_states.translate(mapping_table)

    @property
    def signal_states_sumo(self) -> str:
        """Signal states in SUMO format."""
        return self._sumo_states
