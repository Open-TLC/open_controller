from typing import Any

import numpy as np

from services.control_engine.src.detectors.area_detector import AreaDetector
from services.control_engine.src.geometry.movements import (
    DownstreamMovement,
    LanePressureConfig,
)
from services.control_engine.src.signal_controller import (
    ControllerStatus,
    SignalController,
)

from .configuration import BumblebeeControllerConf
from .rl_util import get_observation, load_model
from .trafficenv import SafetyController


class BumblebeeController(SignalController):
    """Reinforcement learning signal controller."""

    def __init__(
        self,
        conf: BumblebeeControllerConf,
        detectors: dict[str, AreaDetector],
        step_length: float,
    ) -> None:
        """Initialize Bumblebee controller.

        Args:
            conf: Controller configuration for the controller.
            detectors: Detectors by ID.
            step_length: Time step between controller ticks in seconds.

        """
        self._model = load_model(conf.algorithm, conf.model_file)

        self._conf = conf
        self._step_length = step_length

        # Safety controller for handling conflicting phases and intergreens.
        self._safety_controller = SafetyController(
            conf.intergreens,
            step_length,
        )

        self._detectors: list[AreaDetector] = []

        self._lane_pressure_configs: list[LanePressureConfig] = []

        for entry_id in conf.geometry.entry_node_ids():
            upstream_detector = detectors[entry_id]
            self._detectors.append(upstream_detector)

            movements = []
            exit_ids = conf.geometry.exit_node_ids(entry_id)
            for exit_id in exit_ids:
                downstream_detector = detectors[exit_id]
                self._detectors.append(downstream_detector)

                movements.append(
                    DownstreamMovement(
                        downstream_node_id=exit_id,
                        detector=downstream_detector,
                        theta=1,  # TODO: Assign meaningful movement probabilities.
                    ),
                )

            self._lane_pressure_configs.append(
                LanePressureConfig(
                    node_id=entry_id,
                    incoming_detector=upstream_detector,
                    movements=movements,
                ),
            )

        self._cur_phase_idx: int = 0
        self._step_count: int = 0

        self._sumo_states: str = ""

        self._locked: bool = False  # Used to lock the state of the controller to red.

    def tick(self) -> None:
        """Advance the controller by one time step."""
        for detector in self._detectors:
            detector.tick()

        # Controller doesn't advance to new phases if it is locked.
        # This is done to lock it to red in case of a major failure.
        if not self._locked:
            obs = get_observation(
                self._cur_phase_idx,
                len(self._detectors),
                self._lane_pressure_configs,
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
