from math import isclose
from typing import Any

import numpy as np
from gymnasium import spaces
from ray.rllib.env.multi_agent_env import MultiAgentEnv
from ray.rllib.utils.typing import AgentID

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


class MultiTrafficEnv(MultiAgentEnv):
    """RL environment for training multiple signal controller agents."""

    def __init__(
        self,
        simengine: SimEngine,
        env_conf: TrafficEnvConf,
        contr_confs: list[BumblebeeControllerConf],
        det_confs: list[DetectorConfiguration],
    ) -> None:
        super().__init__()

        self._simengine = simengine
        self._contr_confs: list[BumblebeeControllerConf] = contr_confs

        # Length of a training step in seconds.
        if env_conf.step_length <= 0:
            raise ValueError(
                f"Step length ({env_conf.step_length}) must be greater than 0",
            )

        if env_conf.step_length < self._simengine.step_length:
            raise ValueError(
                f"Environment step length ({env_conf.step_length}s) "
                f"cannot be smaller than "
                f"SimEngine step length ({self._simengine.step_length}s).",
            )
        self._step_length: float = env_conf.step_length

        remainder = self._step_length % self._simengine.step_length
        if not (
            isclose(remainder, 0, abs_tol=1e-9)
            or isclose(remainder, self._simengine.step_length, abs_tol=1e-9)
        ):
            raise ValueError(
                f"Environment step length ({self._step_length}s) "
                f"must be a perfect multiple "
                f"of SimEngine step length ({self._simengine.step_length}s). "
                f"Resulting steps would be a fractional "
                f"{self._step_length / self._simengine.step_length}.",
            )

        # How many simulation steps to advance per one environment step.
        self._simulation_steps_per_step: int = round(
            env_conf.step_length / self._simengine.step_length,
        )

        # All detectors are created.
        all_detectors: dict[str, AreaDetector] = {}

        for det_conf in det_confs:
            det_type = det_conf.type
            if det_type == "e1_detector":
                continue
            if det_type == "e2_detector":
                all_detectors[det_conf.id] = E2AreaDetector(det_conf.id)
            elif det_type == "e3_detector":
                all_detectors[det_conf.id] = E3AreaDetector(det_conf.id)
            else:
                raise ValueError(
                    f"Unsupported detector type {det_type} with ID {det_conf.id}.",
                )

        # Create safety controllers.
        self._controllers: dict[AgentID, SafetyController] = {}

        # Track detectors per agent.
        self._detectors: dict[AgentID, list[AreaDetector]] = {}

        # Track pressure configurations per agent.
        self._lane_pressure_configs: dict[AgentID, list[LanePressureConfig]] = {}

        for conf in contr_confs:
            aid = conf.id

            safety_controller = SafetyController(
                conf.intergreens,
                self._simengine.step_length,
            )
            self._controllers[aid] = safety_controller

            agent_detectors: list[AreaDetector] = []
            agent_configs: list[LanePressureConfig] = []

            for entry_id in conf.geometry.entry_node_ids():
                upstream_detector = all_detectors[entry_id]
                if upstream_detector not in agent_detectors:
                    agent_detectors.append(upstream_detector)

                movements = []
                exit_ids = conf.geometry.exit_node_ids(entry_id)
                for exit_id in exit_ids:
                    downstream_detector = all_detectors[exit_id]
                    if downstream_detector not in agent_detectors:
                        agent_detectors.append(downstream_detector)

                    movements.append(
                        DownstreamMovement(
                            downstream_node_id=exit_id,
                            detector=downstream_detector,
                            theta=1.0,  # TODO: Assign meaningful movement probabilities.
                        ),
                    )

                agent_configs.append(
                    LanePressureConfig(
                        node_id=entry_id,
                        incoming_detector=upstream_detector,
                        movements=movements,
                    ),
                )

            self._detectors[aid] = agent_detectors
            self._lane_pressure_configs[aid] = agent_configs

        # IDs of all controllers, i.e. agents.
        self.possible_agents: list[AgentID] = list(self._controllers.keys())
        self.agents: list[AgentID] = self.possible_agents[:]

        self._agent_ids = set(self.possible_agents)

        # Agents have individually shaped action spaces, depending
        # on the number of phases the agent can choose from.
        self.action_spaces = {
            aid: spaces.Discrete(self._controllers[aid].phase_count)
            for aid in self.agents
        }

        # Agents have individually shaped observation spaces,
        # depending on the number of lanes and phases.
        obs_dims: dict[AgentID, int] = {}
        for aid in self._detectors:
            # Observation space for a controller consists of three things:
            # 1. Calculated pressures from incoming lanes.
            # 2. One-hot encoded current phase.
            obs_dims[aid] = (
                len(self._lane_pressure_configs[aid])
                + self._controllers[aid].phase_count
            )

        self.observation_spaces = {
            aid: spaces.Box(
                low=0,
                high=np.inf,
                shape=(obs_dims[aid],),
                dtype=np.float32,
            )
            for aid in self.agents
        }

        # Agents need to know each others' previous actions.
        # All actions are updated here after each step.
        self._actions: dict[AgentID, int] = dict.fromkeys(self.agents, 0)

        # Keep track of actions taken by agents.
        self._action_counts: dict[AgentID, dict[int, int]] = {
            agent: dict.fromkeys(range(self._controllers[agent].phase_count), 0)
            for agent in self.agents
        }

        # Keeps track of episode lengths.
        self._cur_step: int = 0
        self._episode_steps = env_conf.episode_steps

        # Keep track of teleportations.
        self._episode_teleported: int = 0

        # Keep track of total travel time.
        self._episode_travel_time: float = 0

        # Keep track of finished vehicles count.
        self._episode_vehicles: int = 0

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict | None = None,
    ) -> tuple[dict[AgentID, np.ndarray], dict[AgentID, Any]]:
        """Reset the environment to original state."""
        super().reset(seed=seed, options=options)

        self._cur_step: int = 0

        self._episode_teleported = 0
        self._episode_travel_time = 0
        self._episode_vehicles = 0

        # Activate all agents.
        self.agents = self.possible_agents[:]

        # Reset the simulation.
        self._simengine.reset()

        for conf in self._contr_confs:
            safety_controller = SafetyController(
                conf.intergreens,
                self._simengine.step_length,
            )

            self._controllers[conf.id] = safety_controller

        # Update detector states.
        for agent_detectors in self._detectors.values():
            for detector in agent_detectors:
                detector.tick()

        self._actions: dict[AgentID, int] = dict.fromkeys(self.agents, 0)

        self._action_counts: dict[AgentID, dict[int, int]] = {
            agent: dict.fromkeys(range(self._controllers[agent].phase_count), 0)
            for agent in self.agents
        }

        observations = self._get_observations()
        infos = {aid: {} for aid in self.agents}

        return observations, infos

    def step(
        self,
        action_dict: dict[AgentID, int],
    ) -> tuple[
        dict[AgentID, np.ndarray],
        dict[AgentID, float],
        dict[AgentID, bool],
        dict[AgentID, bool],
        dict[AgentID, dict],
    ]:
        """Advance the environment by one timestep using the provided agent actions.

        Applies the agent actions, steps the underlying traffic simulation,
        and updates states.

        Args:
            action_dict: A dictionary mapping active AgentIDs to their chosen actions.

        Returns:
            A tuple containing five dictionaries:
                - obs: New observations mapped by AgentID.
                - rewards: Scalar rewards mapped by AgentID.
                - terminateds: Termination flags mapped by AgentID. Must include
                  the "__all__" key (bool) indicating if the episode ended naturally.
                - truncateds: Truncation flags mapped by AgentID. Must include
                  the "__all__" key (bool) indicating if the episode hit a time limit.
                - infos: Auxiliary diagnostic information mapped by AgentID.

        """
        self._cur_step += 1

        # Update detector states.
        for agent_detectors in self._detectors.values():
            for detector in agent_detectors:
                detector.tick()

        # Apply actions to all controllers.
        for aid in self.agents:
            if aid in action_dict:
                self._action_counts[aid][action_dict[aid]] += 1
                new_states: str = self._controllers[aid].step(action_dict[aid])
                self._simengine.set_signal_group_states(str(aid), new_states)

        # Advance the simulation.
        self._simengine.step(self._simulation_steps_per_step)

        # Save previous actions.
        self._actions = action_dict

        # Gather metric data.
        self._episode_teleported += self._simengine.get_teleported_count
        self._episode_travel_time += self._simengine.get_finished_travel_time
        self._episode_vehicles += self._simengine.get_finished_vehicles_count

        is_truncated = self._cur_step >= self._episode_steps

        observations = self._get_observations()
        rewards = self._get_rewards()

        terminateds = dict.fromkeys(self.agents, False)
        terminateds["__all__"] = False

        truncateds = dict.fromkeys(self.agents, is_truncated)
        truncateds["__all__"] = is_truncated

        infos = {aid: {} for aid in self.agents}

        if is_truncated:
            print(f"Action counts: {self._action_counts}")
            self.agents = []
            print(
                "Average travel time: ",
                self._episode_travel_time / self._episode_vehicles
                if self._episode_vehicles > 0
                else 0,
            )
            print("Vehicles teleported: ", self._episode_teleported)

        return observations, rewards, terminateds, truncateds, infos

    def render(self) -> None:
        """Show current performance in the SUMO GUI."""
        raise NotImplementedError

    def close(self) -> None:
        """Close environment and simulation."""
        self._simengine.close()

    def _get_observations(self) -> dict[AgentID, np.ndarray]:
        observations: dict[AgentID, np.ndarray] = {}
        for aid in self.agents:
            cur_phase_idx = self._actions[aid]
            phase_count = self._controllers[aid].phase_count
            pressure_configs = self._lane_pressure_configs[aid]

            individual_observation = get_observation(
                cur_phase_idx,
                phase_count,
                pressure_configs,
            )

            observations[aid] = individual_observation

        return observations

    def _get_rewards(self) -> dict[AgentID, float]:
        """Calculate reward for the last step for all agents.

        Returns:
            Dict mapping agent_id to its local reward as a negative float.

        """
        rewards = {}

        for aid in self.agents:
            rewards[aid] = get_presslight_reward(self._lane_pressure_configs[aid])
        return rewards
