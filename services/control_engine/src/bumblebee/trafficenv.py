from itertools import product
from typing import Any

import gymnasium
import numpy as np

from .configuration import TrafficEnvConf
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

    def __init__(self, simengine: SimEngine, conf: TrafficEnvConf) -> None:
        self._simengine = simengine
        self._controller_id: str = conf.sumo_name

        # How many simulation steps to advance per one environment step.
        self._simulation_steps_per_step: int = conf.simulation_step_count

        # Length of the simulated step in seconds.
        self._step_length: float = (
            self._simengine.get_step_length() * self._simulation_steps_per_step
        )

        self._intergreens = np.array(conf.intergreens)

        # List of all legal state combinations.
        self._phases: np.ndarray = self._get_possible_phases(self._intergreens)

        # Safety controller for handling conflicting phases and intergreens.
        self._safety_controller = SafetyController(self._intergreens, self._step_length)

        # Action space maps a discrete number to a possible phase.
        self._action_space = gymnasium.spaces.Discrete(self._phases.shape[0])

        # Track the state of the controller.
        self._cur_phase_idx = 0

    def reset(
        self, *, options: dict | None = None, seed: int | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        print(options)

        # Reset the simulation.
        self._simengine.reset()

        # Reset the controller.
        self._safety_controller = SafetyController(self._intergreens, self._step_length)

        self._cur_phase_idx = 0
        observation: np.ndarray = self._get_observation()
        info: dict[str, Any] = {"message": "Not implemented"}
        return observation, info

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        self._cur_phase_idx = action
        # TODO: Currently signal group states are only updated once per step. This
        # doesn't take into consideration that the intergreen times can expire between
        # simulation steps. This isn't likely a major problem, since once per sec is
        # still frequent enough and intergreen times are usually full seconds.

        # Turn action to SUMO state string.
        new_states = self._get_group_states(action)

        # Set signal group states in simulation to the new states.
        self._simengine.set_signal_group_states(self._controller_id, new_states)

        # Advance the simulation.
        self._simengine.step(self._simulation_steps_per_step)

        observation: np.ndarray = self._get_observation()
        reward: float = self._reward()
        terminated: bool = len(self._simengine.get_teleported()) > 0
        truncated: bool = len(self._simengine.get_teleported()) > 0
        info: dict[str, Any] = {"message": "Not implemented"}

        return observation, reward, terminated, truncated, info

    def render(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        self._simengine.close()

    def _get_observation(self) -> np.ndarray:
        self._detector_readings = self._simengine.get_detector_readings()

        traffic_information = np.array(
            [list(area.values()) for area in self._detector_readings]
        )

        # Current phase is added so agent can know
        # the previous state of the controller.
        return np.append(traffic_information, self._cur_phase_idx)

    def _get_group_states(self, phase_idx: int) -> str:
        new_phase: np.ndarray = self._phases[phase_idx]
        new_states = self._safety_controller.step(new_phase)

        return new_states

    def _reward(self) -> float:
        """Calculate reward for last step.

        Returns:
            Reward as a negative number. Higher means better performance.
        """
        wait_times = np.array(
            [reading["average_time_loss"] for reading in self._detector_readings]
        )

        if wait_times.size == 0:
            return 0.0

        mean_square = np.mean(wait_times**2)

        return -float(mean_square)

    def _get_possible_phases(self, intergreens: np.ndarray) -> np.ndarray:
        """Get all possible phases based on the intergreen matrix.

        Args:
            intergreens: Intergreen times as a matrix. Each row represents an
                origin group and each column the target group. Each element is
                the shortest time between the origin and target group.

        Returns:
            List of possible phases as a 2D matrix. 1 means green and 0 means red.
        """
        num_groups = intergreens.shape[0]

        # Groups conflict if either origin->target or
        # target->origin requires intergreen time > 0.
        conflict_matrix = (intergreens > 0) | (intergreens.T > 0)

        # Group doesn't conflict with itself.
        np.fill_diagonal(conflict_matrix, False)

        possible_phases = []

        # Generate all possible binary combinations for groups.
        for phase in product([0, 1], repeat=num_groups):
            phase_arr = np.array(phase)

            # Get indices of all groups that want to be green (1).
            green_indices = np.where(phase_arr == 1)[0]

            # Extract conflicts between green groups from conflict matrix.
            conflicting_greens = conflict_matrix[np.ix_(green_indices, green_indices)]

            # If phase doesn't contain conflicting green's,
            # it is added to the list of possible phases.
            if not np.any(conflicting_greens):
                possible_phases.append(phase_arr)

        if len(possible_phases) == 0:
            raise ValueError("No possible phases in intergreen matrix")

        return np.array(possible_phases)
