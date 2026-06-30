from itertools import product

import numpy as np


class SafetyController:
    def __init__(
        self,
        logical_intergreens: np.ndarray,
        link_to_logical_map: list[int],
        step_length: float,
        default_yellow: float = 3.0,
    ) -> None:
        """
        Args:
            logical_intergreens: N x N matrix of transition times between *logical* signal groups.
            link_to_logical_map: List mapping SUMO link index to logical group index.
                                 e.g., [0, 1, 0, 2, 3]
            step_length: Length of a time step in seconds.
            default_yellow: Length of yellow light.
        """
        self._intergreens = logical_intergreens
        self._link_map = link_to_logical_map
        self._delta_t = step_length
        self._default_yellow = default_yellow

        self._num_logical = logical_intergreens.shape[0]
        self._current_group_states = ["r"] * self._num_logical
        self._yellow_timers = np.zeros(self._num_logical)
        self._lockout_timers = np.zeros(self._num_logical)

        self._phases = self._get_possible_phases()

    @property
    def phase_count(self) -> int:
        return self._phases.shape[0]

    def step(self, new_phase_idx: int) -> str:
        new_phase = self._phases[new_phase_idx]

        # Green -> Yellow transitions.
        for i in range(self._num_logical):
            if self._current_group_states[i] == "g" and new_phase[i] == 0:
                self._current_group_states[i] = "y"
                self._yellow_timers[i] = self._default_yellow

                for j in range(self._num_logical):
                    if i != j and self._intergreens[i, j] > 0:
                        self._lockout_timers[j] = max(
                            self._lockout_timers[j], self._intergreens[i, j]
                        )

        # Yellow -> Red transitions and lockout timings.
        for i in range(self._num_logical):
            if self._yellow_timers[i] > 0:
                self._yellow_timers[i] = max(
                    0.0, self._yellow_timers[i] - self._delta_t
                )

            if self._current_group_states[i] == "y" and self._yellow_timers[i] <= 0.0:
                if new_phase[i] == 0:
                    self._current_group_states[i] = "r"

            if self._lockout_timers[i] > 0:
                self._lockout_timers[i] = max(
                    0.0, self._lockout_timers[i] - self._delta_t
                )

        # Red -> Green transitions.
        for j in range(self._num_logical):
            if new_phase[j] == 1 and self._current_group_states[j] != "g":
                conflict_active = False
                for i in range(self._num_logical):
                    if self._intergreens[i, j] > 0 and self._current_group_states[
                        i
                    ] in ["g", "y"]:
                        conflict_active = True
                        break

                if self._lockout_timers[j] <= 0 and not conflict_active:
                    self._current_group_states[j] = "g"
                    self._yellow_timers[j] = 0.0

        # Map Logical States -> Physical SUMO String.
        sumo_state = [
            self._current_group_states[logical_idx] for logical_idx in self._link_map
        ]
        return "".join(sumo_state)

    def _get_possible_phases(self) -> np.ndarray:
        conflict_matrix = (self._intergreens > 0) | (self._intergreens.T > 0)
        np.fill_diagonal(conflict_matrix, False)

        # Generate all phase with no conflicts.
        valid_phases = []
        for phase in product([0, 1], repeat=self._num_logical):
            phase_arr = np.array(phase)
            green_indices = np.where(phase_arr == 1)[0]

            if len(green_indices) > 0:
                conflicting_greens = conflict_matrix[
                    np.ix_(green_indices, green_indices)
                ]
                if not np.any(conflicting_greens):
                    valid_phases.append(phase_arr)
            else:
                valid_phases.append(phase_arr)  # All red

        phases_array = np.array(valid_phases)
        maximal_phases = []

        # Filter out phases that aren't maximal, meaning that they are subsets of
        # other groups. This is done to reduce the number of phases.
        for i, phase in enumerate(phases_array):
            is_maximal = True
            for j, other in enumerate(phases_array):
                if i == j:
                    continue
                if np.all((phase | other) == other) and not np.array_equal(
                    phase, other
                ):
                    is_maximal = False
                    break
            if is_maximal:
                maximal_phases.append(phase)

        # To give the agent granular control over traffic, single group phases are
        # added. This means phases where only one group is green. The idea here is
        # that the agent can avoid unnecessary intergreen times if letting only a
        # single vehicle through.
        # TODO: Evaluate the usefulness of these extra phases.
        single_phases = np.eye(self._num_logical, dtype=int)

        # All red phase is also added. This can be used as a "waiting" state if no
        # vehicles are around.
        # TODO: Evaluate the usefulness of this extra phase.
        all_red = np.zeros((1, self._num_logical), dtype=int)

        # All phases are combined.
        final_phases = np.vstack([maximal_phases, single_phases, all_red])

        # Duplicates are removed.
        return np.unique(final_phases, axis=0)
