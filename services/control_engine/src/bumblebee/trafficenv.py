from math import isclose
from typing import Any

import gymnasium
import numpy as np

from services.control_engine.src.detectors.area_detector import AreaDetector
from services.control_engine.src.detectors.configuration import DetectorConfiguration
from services.control_engine.src.detectors.sumo_e2_detector import E2AreaDetector
from services.control_engine.src.detectors.sumo_e3_detector import E3AreaDetector
from services.control_engine.src.geometry.movements import (
    DownstreamMovement,
    LanePressureConfig,
)

from .configuration import BumblebeeControllerConf, TrafficEnvConf
from .rl_util import get_observation, get_presslight_reward
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
        contr_conf: BumblebeeControllerConf,
        det_confs: list[DetectorConfiguration],
    ) -> None:
        self._simengine = simengine
        self._controller_id: str = contr_conf.id
        self._contr_conf = contr_conf

        # Length of a training step in seconds.
        if env_conf.step_length <= 0:
            raise ValueError(
                f"Step length ({env_conf.step_length}) must be greater than 0",
            )

        if env_conf.step_length < self._simengine.step_length:
            raise ValueError(
                f"Environment step length ({env_conf.step_length}s) cannot be "
                f"smaller than SimEngine step length ({self._simengine.step_length}s).",
            )
        self._step_length: float = env_conf.step_length

        remainder = self._step_length % self._simengine.step_length
        if not (
            isclose(remainder, 0, abs_tol=1e-9)
            or isclose(remainder, self._simengine.step_length, abs_tol=1e-9)
        ):
            raise ValueError(
                f"Environment step length ({self._step_length}s) must be a perfect "
                f"multiple of SimEngine step length ({self._simengine.step_length}s). "
                f"Resulting steps would be a fractional "
                f"{self._step_length / self._simengine.step_length}.",
            )

        # How many simulation steps to advance per one environment step.
        self._simulation_steps_per_step: int = round(
            env_conf.step_length / self._simengine.step_length,
        )

        # Safety controller for handling conflicting phases and intergreens.
        self._safety_controller = SafetyController(
            contr_conf.intergreens,
            self._simengine.step_length,
        )

        # Create detectors.
        detectors: dict[str, AreaDetector] = {}

        for det_conf in det_confs:
            det_type = det_conf.type
            if det_type == "e1_detector":
                continue
            if det_type == "e2_detector":
                detectors[det_conf.id] = E2AreaDetector(det_conf.id)
            elif det_type == "e3_detector":
                detectors[det_conf.id] = E3AreaDetector(det_conf.id)
            else:
                raise ValueError(
                    f"Unsupported detector type {det_type} with ID {det_conf.id}.",
                )

        self._detectors: list[AreaDetector] = []

        self._lane_pressure_configs: list[LanePressureConfig] = []

        for entry_id in contr_conf.geometry.entry_node_ids():
            upstream_detector = detectors[entry_id]
            self._detectors.append(upstream_detector)

            movements = []
            exit_ids = contr_conf.geometry.exit_node_ids(entry_id)
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

        # Action space maps a discrete number to a possible phase.
        self.action_space = gymnasium.spaces.Discrete(
            self._safety_controller.phase_count,
        )

        # Incoming lanes contribute one pressure each
        # and phase is one-hot encoded on top.
        obs_dim = len(self._lane_pressure_configs) + self._safety_controller.phase_count

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

        # Keep track of actions.
        self._action_counts: dict[int, int] = dict.fromkeys(
            range(self._safety_controller.phase_count),
            0,
        )

    def reset(
        self,
        *,
        options: dict | None = None,
        seed: int | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)

        print(f"Action counts: {self._action_counts}")
        self._action_counts: dict[int, int] = dict.fromkeys(
            range(self._safety_controller.phase_count),
            0,
        )

        self._episode_teleported = 0

        self._episode_travel_time = 0
        self._episode_vehicles = 0

        self._episode_reward = 0

        # Reset the simulation.
        self._simengine.reset()

        # Reset the controller.
        self._safety_controller = SafetyController(
            self._contr_conf.intergreens,
            self._simengine.step_length,
        )

        self._cur_phase_idx = 0
        self._cur_step = 0

        # Update detector states.
        for detector in self._detectors:
            detector.tick()

        observation: np.ndarray = get_observation(
            self._cur_phase_idx,
            self._safety_controller.phase_count,
            self._lane_pressure_configs,
        )

        info: dict[str, Any] = {"status": "initialized"}
        return observation, info

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        self._cur_step += 1
        self._cur_phase_idx = action
        self._action_counts[action] += 1
        # TODO: Currently signal group states are only updated once per step. This
        # doesn't take into consideration that the intergreen times can expire between
        # simulation steps. This isn't likely a major problem, since once per sec is
        # still frequent enough and intergreen times are usually full seconds.

        # Update detector states.
        for detector in self._detectors:
            detector.tick()

        # Turn action to SUMO state string.
        new_states = self._safety_controller.step(action)

        # Set signal group states in simulation to the new states.
        self._simengine.set_signal_group_states(self._controller_id, new_states)

        # Advance the simulation.
        self._simengine.step(self._simulation_steps_per_step)

        observation: np.ndarray = get_observation(
            self._cur_phase_idx,
            self._safety_controller.phase_count,
            self._lane_pressure_configs,
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
        return get_presslight_reward(self._lane_pressure_configs)
