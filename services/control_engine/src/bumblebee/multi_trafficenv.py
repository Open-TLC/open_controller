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

        self._simengine: SimEngine = simengine
        self._contr_confs: list[BumblebeeControllerConf] = contr_confs

        self._step_length, self._simulation_steps_per_step = (
            self._validate_and_calc_step_length(env_conf.step_length)
        )

        # Create all detectors.
        all_detectors = self._create_detector_registry(det_confs)

        # Setup safety controllers, agent detectors, and pressure configs
        self._controllers: dict[AgentID, SafetyController] = {}
        self._detectors: dict[AgentID, list[AreaDetector]] = {}
        self._lane_pressure_configs: dict[AgentID, list[LanePressureConfig]] = {}
        self._setup_agent_controllers_and_configs(contr_confs, all_detectors)

        # Assign agents.
        self.possible_agents: list[AgentID] = list(self._controllers.keys())
        self.agents: list[AgentID] = self.possible_agents[:]
        self._agent_ids: set[AgentID] = set(self.possible_agents)

        # Define action and observation spaces.
        self.action_spaces: dict[AgentID, spaces.Space] | None = (
            self._build_action_spaces()
        )
        self.observation_spaces: dict[AgentID, spaces.Space] | None = (
            self._build_observation_spaces()
        )

        # Setup training trackers.
        self._init_state_trackers(env_conf.episode_steps)

    def _validate_and_calc_step_length(
        self,
        env_step_length: float,
    ) -> tuple[float, int]:
        """Validate step length constraints against SimEngine step length."""
        sim_step_length = self._simengine.step_length

        if env_step_length <= 0:
            raise ValueError(
                f"Step length ({env_step_length}) must be greater than 0",
            )

        if env_step_length < sim_step_length:
            raise ValueError(
                f"Environment step length ({env_step_length}s) "
                f"cannot be smaller than "
                f"SimEngine step length ({sim_step_length}s).",
            )

        remainder = env_step_length % sim_step_length
        if not (
            isclose(remainder, 0, abs_tol=1e-9)
            or isclose(remainder, sim_step_length, abs_tol=1e-9)
        ):
            raise ValueError(
                f"Environment step length ({env_step_length}s) "
                f"must be a perfect multiple "
                f"of SimEngine step length ({sim_step_length}s). "
                f"Resulting steps would be a fractional "
                f"{env_step_length / sim_step_length}.",
            )

        simulation_steps = round(env_step_length / sim_step_length)
        return env_step_length, simulation_steps

    def _create_detector_registry(
        self,
        det_confs: list[DetectorConfiguration],
    ) -> dict[str, AreaDetector]:
        """Instantiate and register all supported detectors."""
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

        return all_detectors

    def _setup_agent_controllers_and_configs(
        self,
        contr_confs: list[BumblebeeControllerConf],
        all_detectors: dict[str, AreaDetector],
    ) -> None:
        """Initialize controllers and map entry/exit detectors for controllers."""
        for conf in contr_confs:
            aid = conf.id

            self._controllers[aid] = SafetyController(
                conf.intergreens,
                conf.geometry,
                self._simengine.step_length,
            )

            agent_detectors, agent_configs = self._build_agent_pressure_configs(
                conf,
                all_detectors,
            )
            self._detectors[aid] = agent_detectors
            self._lane_pressure_configs[aid] = agent_configs

    def _build_agent_pressure_configs(
        self,
        conf: BumblebeeControllerConf,
        all_detectors: dict[str, AreaDetector],
    ) -> tuple[list[AreaDetector], list[LanePressureConfig]]:
        """Create lane pressure configs and detectors for a controller."""
        agent_detectors: list[AreaDetector] = []
        agent_configs: list[LanePressureConfig] = []

        for entry_id in conf.geometry.entry_node_ids():
            upstream_detector = all_detectors[entry_id]
            if upstream_detector not in agent_detectors:
                agent_detectors.append(upstream_detector)

            movements: list[DownstreamMovement] = []
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

        return agent_detectors, agent_configs

    def _build_action_spaces(self) -> dict[AgentID, spaces.Space]:
        """Create action spaces based on controller phase counts."""
        return {
            aid: spaces.Discrete(self._controllers[aid].phase_count)
            for aid in self.agents
        }

    def _build_observation_spaces(self) -> dict[AgentID, spaces.Space]:
        """Create observation spaces based on lane pressure configurations."""
        obs_dims: dict[AgentID, int] = {
            aid: len(self._lane_pressure_configs[aid])
            + self._controllers[aid].phase_count
            + 1
            for aid in self._detectors
        }

        return {
            aid: spaces.Box(
                low=0,
                high=np.inf,
                shape=(obs_dims[aid],),
                dtype=np.float32,
            )
            for aid in self.agents
        }

    def _init_state_trackers(self, episode_steps: int) -> None:
        """Initialize trackers for actions and phase changes."""
        self._actions: dict[AgentID, int] = dict.fromkeys(self.agents, 0)
        self._action_counts: dict[AgentID, dict[int, int]] = {
            agent: dict.fromkeys(
                range(self._controllers[agent].phase_count),
                0,
            )
            for agent in self.agents
        }

        self._cur_step: int = 0
        self._episode_steps: int = episode_steps

        self._episode_travel_time: float = 0.0
        self._episode_vehicles: int = 0

        self._cur_phases: dict[AgentID, int] = dict.fromkeys(
            self.possible_agents,
            0,
        )
        self._phase_changes: dict[AgentID, int] = dict.fromkeys(
            self.possible_agents,
            0,
        )

        self._steps_since_phase_start: dict[AgentID, int] = dict.fromkeys(
            self.possible_agents,
            0,
        )

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict | None = None,
    ) -> tuple[dict[AgentID, np.ndarray], dict[AgentID, Any]]:
        """Reset the environment to original state."""
        super().reset(seed=seed, options=options)

        self._cur_step: int = 0

        self._episode_travel_time = 0
        self._episode_vehicles = 0
        self._cur_phases = dict.fromkeys(self.possible_agents, 0)
        self._phase_changes = dict.fromkeys(self.possible_agents, 0)
        self._steps_since_phase_start = dict.fromkeys(self.possible_agents, 0)

        # Activate all agents.
        self.agents = self.possible_agents[:]

        # Reset the simulation.
        self._simengine.reset()

        for conf in self._contr_confs:
            safety_controller = SafetyController(
                conf.intergreens,
                conf.geometry,
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
                if self._cur_phases[aid] != action_dict[aid]:
                    self._phase_changes[aid] += 1
                    self._steps_since_phase_start[aid] = 0
                self._steps_since_phase_start[aid] += 1
                self._cur_phases[aid] = action_dict[aid]
                self._action_counts[aid][action_dict[aid]] += 1
                new_states: str = self._controllers[aid].step(action_dict[aid])
                self._simengine.set_signal_group_states(str(aid), new_states)

        # Advance the simulation.
        self._simengine.step(self._simulation_steps_per_step)

        # Save previous actions.
        self._actions = action_dict

        # Gather metric data.
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
                round(self._episode_travel_time / self._episode_vehicles, 1)
                if self._episode_vehicles > 0
                else 0,
            )
            print("Number of trips: ", self._episode_vehicles)
            print(f"Phase changes: {self._phase_changes}\n")

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
                self._steps_since_phase_start[aid],
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
