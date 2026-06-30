from math import isclose
from typing import Any

import gymnasium
import numpy as np

from services.control_engine.src.detectors.area_detector import AreaDetector
from services.control_engine.src.detectors.sumo_e2_detector import E2AreaDetector
from services.control_engine.src.detectors.sumo_e3_detector import E3AreaDetector

from .configuration import ControllerConf, TrafficEnvConf
from .rl_util import get_observation
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
        env_conf: TrafficEnvConf,
        contr_conf: ControllerConf,
    ) -> None:
        self._simengine = simengine
        self._controller_id: str = contr_conf.name

        # Length of a training step in seconds.
        if env_conf.step_length <= 0:
            raise ValueError(
                f"Step length ({env_conf.step_length}) must be greater than 0"
            )

        if env_conf.step_length < self._simengine.step_length:
            raise ValueError(
                f"Environment step length ({env_conf.step_length}s) cannot be smaller than "
                f"SimEngine step length ({self._simengine.step_length}s)."
            )
        self._step_length: float = env_conf.step_length

        remainder = self._step_length % self._simengine.step_length
        if not (
            isclose(remainder, 0, abs_tol=1e-9)
            or isclose(remainder, self._simengine.step_length, abs_tol=1e-9)
        ):
            raise ValueError(
                f"Environment step length ({self._step_length}s) must be a perfect multiple "
                f"of SimEngine step length ({self._simengine.step_length}s). "
                f"Resulting steps would be a fractional {self._step_length / self._simengine.step_length}."
            )

        # How many simulation steps to advance per one environment step.
        self._simulation_steps_per_step: int = round(
            env_conf.step_length / self._simengine.step_length
        )

        self._intergreens = np.array(contr_conf.intergreens)
        self._group_outputs = contr_conf.group_outputs

        # Safety controller for handling conflicting phases and intergreens.
        self._safety_controller = SafetyController(
            self._intergreens, self._group_outputs, self._simengine.step_length
        )

        # Action space maps a discrete number to a possible phase.
        self.action_space = gymnasium.spaces.Discrete(
            self._safety_controller.phase_count
        )

        self._detectors: list[AreaDetector] = []
        for detector_conf in contr_conf.detector_confs:
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

        # Detectors provide 1 reading each and phase is one-hot encoded on top.
        obs_dim = len(self._detectors) + self._safety_controller.phase_count

        self.observation_space = gymnasium.spaces.Box(
            low=0,
            high=np.inf,
            shape=(obs_dim,),
            dtype=np.float32,
        )

        # Keep track of steps.
        self._cur_step: int = 0
        self._episode_max_steps = env_conf.episode_steps

        # Keep track of teleportations.
        self._episode_teleported: int = 0

        # Keep track of total travel time.
        self._episode_travel_time: float = 0

        # Keep track of finished vehicles count.
        self._episode_vehicles: int = 0

        # Keep track of cumulative reward.
        self._episode_reward: float = 0

    def reset(
        self, *, options: dict | None = None, seed: int | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)

        self._episode_teleported = 0

        self._episode_travel_time = 0
        self._episode_vehicles = 0

        self._episode_reward = 0

        # Reset the simulation.
        self._simengine.reset()

        # Reset the controller.
        self._safety_controller = SafetyController(
            self._intergreens, self._group_outputs, self._simengine.step_length
        )

        self._cur_phase_idx = 0
        self._cur_step = 0

        observation: np.ndarray = get_observation(
            self._cur_phase_idx, self._safety_controller.phase_count, self._detectors
        )

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

        observation: np.ndarray = get_observation(
            self._cur_phase_idx, self._safety_controller.phase_count, self._detectors
        )

        reward: float = self._reward()

        # Gather metric data.
        self._episode_teleported += self._simengine.get_teleported_count
        self._episode_travel_time += self._simengine.get_finished_travel_time
        self._episode_vehicles += self._simengine.get_finished_vehicles_count
        self._episode_reward += reward

        terminated: bool = self._cur_step > self._episode_max_steps
        truncated: bool = False

        info = {}

        if terminated or truncated:
            info["traffic"] = {
                "teleported": self._episode_teleported,
                "finished": self._episode_vehicles,
                "avg_travel_time": (
                    self._episode_travel_time / self._episode_vehicles
                    if self._episode_vehicles > 0
                    else 0
                ),
            }
            info["metrics"] = {
                "reward": self._episode_reward,
            }

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
        teleport_penalty = self._simengine.get_teleported_count * -1000

        queue_lengths = np.array(
            [d.vehicle_count() for d in self._detectors], dtype=np.float32
        )

        # This is a threshold for approximating the number of cars that fit in
        # a detectors area. If this is exceeded, the queue spills out of the
        # detection area and the reward is adjusted to prevent this.
        QUEUE_THRESHOLD: float = 8

        exceeds_mask = queue_lengths > QUEUE_THRESHOLD
        penalties = np.where(
            exceeds_mask,
            QUEUE_THRESHOLD + (queue_lengths - QUEUE_THRESHOLD) ** 2,
            queue_lengths,
        )

        return teleport_penalty - float(np.sum(penalties))
