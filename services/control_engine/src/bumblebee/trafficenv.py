from typing import Any

import gymnasium
import numpy as np

from services.control_engine.src.detectors.area_detector import AreaDetector
from services.control_engine.src.detectors.sumo_e2_detector import E2AreaDetector
from services.control_engine.src.detectors.sumo_e3_detector import E3AreaDetector

from .configuration import TrafficEnvConf
from .rl_util import get_detector_readings, get_observation
from .safety_controller import SafetyController
from .simengine import SimEngine


class TrafficEnv(gymnasium.Env):
    """TrafficEnv is used to train and run RL models in Open Controller Bumblebee.
    TrafficEnv uses SimEngine and SUMO to simulate traffic on a network. It can
    provide observations based on detector readings from the simulation, execute
    signal group states, and calculate statistics about the traffic situation. The
    environment is also responsible for ensuring the safety of traffic by blocking
    conflicting signal phases.
    """

    def __init__(
        self,
        simengine: SimEngine,
        conf: TrafficEnvConf,
    ) -> None:
        self._simengine = simengine
        self._simengine.reset()
        self._controller_id: str = conf.sumo_name

        # How many simulation steps to advance per one environment step.
        self._simulation_steps_per_step: int = conf.simulation_step_count

        # Length of the simulated step in seconds.
        self._step_length: float = (
            self._simengine.get_step_length() * self._simulation_steps_per_step
        )

        self._intergreens = np.array(conf.intergreens)

        # Safety controller for handling conflicting phases and intergreens.
        self._safety_controller = SafetyController(self._intergreens, self._step_length)

        # Action space maps a discrete number to a possible phase.
        self.action_space = gymnasium.spaces.Discrete(
            self._safety_controller.phase_count
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
                    f"Unknown detector type for detector {det_id}: {det_type}"
                )
            self._detectors.append(detector)

        # Each detector provides 1 value and current phase is added on top.
        obs_dim = len(self._detectors) + 1

        self.observation_space = gymnasium.spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(obs_dim,),
            dtype=np.float32,
        )

        # Track the state of the controller.
        self._cur_phase_idx = 0

        # Keep track of steps.
        self._cur_step = 0
        self._episode_max_steps = conf.episode_steps

    def reset(
        self, *, options: dict | None = None, seed: int | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)

        # Reset the simulation.
        self._simengine.reset()

        # Reset the controller.
        self._safety_controller = SafetyController(self._intergreens, self._step_length)

        self._cur_phase_idx = 0
        self._cur_step = 0

        observation: np.ndarray = get_observation(self._cur_phase_idx, self._detectors)
        info: dict[str, Any] = {"status": "initialized"}
        return observation, info

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        self._cur_step += 1
        self._cur_phase_idx = action
        # TODO: Currently signal group states are only updated once per step. This
        # doesn't take into consideration that the intergreen times can expire between
        # simulation steps. This isn't likely a major problem, since once per sec is
        # still frequent enough and intergreen times are usually full seconds.

        # Turn action to SUMO state string.
        new_states = self._safety_controller.step(action)

        # Set signal group states in simulation to the new states.
        self._simengine.set_signal_group_states(self._controller_id, new_states)

        # Advance the simulation.
        self._simengine.step(self._simulation_steps_per_step)

        observation: np.ndarray = get_observation(self._cur_phase_idx, self._detectors)
        reward: float = self._reward()
        terminated: bool = (
            len(self._simengine.get_teleported()) > 0
            or self._cur_step > self._episode_max_steps
        )
        truncated: bool = False
        info: dict[str, Any] = {"current_phase": action}

        return observation, reward, terminated, truncated, info

    def render(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        self._simengine.close()

    def _reward(self) -> float:
        """Calculate reward for last step.

        Returns:
            Reward as a negative number. Higher means better performance.
        """
        teleported: int = len(self._simengine.get_teleported())

        reward = teleported * (-1000)

        readings = get_detector_readings(self._detectors)

        queue_lengths = np.array([reading["vehicle_count"] for reading in readings])

        if queue_lengths.size == 0:
            return reward

        return reward - float(np.sum(queue_lengths))
