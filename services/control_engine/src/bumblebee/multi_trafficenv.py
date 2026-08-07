from math import isclose
from typing import Any

import numpy as np
from gymnasium import spaces
from ray.rllib.env.multi_agent_env import MultiAgentEnv
from ray.rllib.utils.typing import AgentID

from services.control_engine.src.detectors.area_detector import (
    AreaDetector,
    TransitAreaDetector,
)
from services.control_engine.src.detectors.configuration import (
    DetectorConfiguration,
    create_detectors,
)
from services.control_engine.src.geometry.movements import (
    DownstreamMovement,
    LanePressureConfig,
)
from services.control_engine.src.timer import Timer

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
        all_detectors: dict[str, AreaDetector],
    ) -> None:
        """Create a new MultiTrafficEnv.

        Prefer using `MultiTrafficEnv.create(...)` to ensure detectors are
        asynchronously initialized before environment setup.

        Args:
            simengine: Simulation engine used by the environment.
            env_conf: Traffic environment configuration.
            contr_confs: List of controller configurations.
            all_detectors: Pre-initialized detector registry.

        """
        super().__init__()

        self._simengine: SimEngine = simengine

        self._timer = Timer(
            {
                "timer_mode": "fixed",
                "real_time_multiplier": 1,
                "time_step": env_conf.step_length,
            },
        )

        self._contr_confs: list[BumblebeeControllerConf] = contr_confs

        self._step_length, self._simulation_steps_per_step = (
            self._validate_and_calc_step_length(env_conf.step_length)
        )

        # Setup safety controllers, agent detectors, and pressure configs.
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

    @classmethod
    async def create(
        cls,
        simengine: SimEngine,
        env_conf: TrafficEnvConf,
        contr_confs: list[BumblebeeControllerConf],
        det_confs: list[DetectorConfiguration],
    ) -> "MultiTrafficEnv":
        """Asynchronously create a MultiTrafficEnv instance.

        Args:
            simengine: Simulation engine instance.
            env_conf: Traffic environment configuration.
            contr_confs: List of controller configurations for agents.
            det_confs: List of detector configurations to instantiate.

        Returns:
            Fully initialized MultiTrafficEnv instance.

        """
        all_detectors = await cls._create_detector_registry(det_confs)

        return cls(
            simengine=simengine,
            env_conf=env_conf,
            contr_confs=contr_confs,
            all_detectors=all_detectors,
        )

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

    @staticmethod
    async def _create_detector_registry(
        det_confs: list[DetectorConfiguration],
    ) -> dict[str, AreaDetector]:
        """Instantiate and register all supported detectors."""
        _, area_detectors = await create_detectors(det_confs)

        all_detectors: dict[str, AreaDetector] = {}

        for det in area_detectors:
            all_detectors[det.id] = det

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
                self._timer,
            )

            agent_detectors, agent_configs = self._build_agent_pressure_configs(
                conf,
                all_detectors,
            )
            self._detectors[aid] = agent_detectors
            self._lane_pressure_configs[aid] = agent_configs

        # Save filtered transit detectors.
        self._transit_detectors: dict[AgentID, list[TransitAreaDetector]] = {
            aid: [det for det in detectors if isinstance(det, TransitAreaDetector)]
            for aid, detectors in self._detectors.items()
        }

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

        # Add special transit detectors.
        for entry_id in conf.transit_links:
            transit_det = all_detectors[f"transit_{entry_id}"]
            agent_detectors.append(transit_det)

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
            + len(self._transit_detectors[aid])
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
        self._episode_transit_time: float = 0
        self._episode_transit_count: int = 0

        self._cur_phases: dict[AgentID, int] = dict.fromkeys(
            self.possible_agents,
            0,
        )
        self._phase_changes: dict[AgentID, int] = dict.fromkeys(
            self.possible_agents,
            0,
        )

        self._phase_start_times: dict[AgentID, float] = dict.fromkeys(
            self.possible_agents,
            float(self._timer.seconds),
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
        self._episode_transit_time = 0
        self._episode_transit_count = 0

        self._cur_phases = dict.fromkeys(self.possible_agents, 0)
        self._phase_changes = dict.fromkeys(self.possible_agents, 0)
        self._phase_start_times = dict.fromkeys(
            self.possible_agents,
            float(self._timer.seconds),
        )

        # Activate all agents.
        self.agents = self.possible_agents[:]

        # Reset the simulation.
        self._simengine.reset()

        for conf in self._contr_confs:
            safety_controller = SafetyController(
                conf.intergreens,
                conf.geometry,
                self._timer,  # Timer doesn't need resetting between environment resets.
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

        # Update timer so controllers will update their timings.
        self._timer.tick()

        # Update detector states.
        for agent_detectors in self._detectors.values():
            for detector in agent_detectors:
                detector.tick()

        # Apply actions to all controllers.
        for aid in self.agents:
            if aid in action_dict:
                # Transition to a new phase.
                if self._cur_phases[aid] != action_dict[aid]:
                    self._phase_changes[aid] += 1
                    self._phase_start_times[aid] = float(self._timer.seconds)

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
        self._episode_transit_time += self._simengine.get_finished_transit_time
        self._episode_transit_count += self._simengine.get_finished_transit_count

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
            print(
                "Average transit travel time: ",
                round(self._episode_transit_time / self._episode_transit_count, 1)
                if self._episode_transit_count > 0
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

            elapsed_time = self._phase_start_times[aid] - self._timer.seconds

            transit_detections: np.ndarray = np.array(
                [det.vehicle_count for det in self._transit_detectors[aid]],
                dtype=np.float32,
            )

            individual_observation = get_observation(
                cur_phase_idx,
                elapsed_time,
                phase_count,
                pressure_configs,
                transit_detections,
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
            rewards[aid] = get_presslight_reward(
                self._lane_pressure_configs[aid],
                self._transit_detectors[aid],
            )
        return rewards
