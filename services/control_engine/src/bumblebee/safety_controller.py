from itertools import product

import numpy as np


class SafetyController:
    def __init__(
        self, intergreens: np.ndarray, step_length: float, default_yellow: float = 3
    ) -> None:
        """Controller for handling transitions from state to another safely.

        Args:
            intergreens: N x N matrix of transition times between signal groups.
            step_length: Length of a time step in seconds.
            default_yellow: Length of yellow light. This can't be lower than any of
                intergreen times.
        """
        self._intergreens = intergreens
        self._delta_t = step_length
        self._default_yellow = default_yellow
        self._num_groups = intergreens.shape[0]

        conflicting_intergreens = intergreens[intergreens > 0]

        if conflicting_intergreens.size > 0:
            if np.min(conflicting_intergreens) < default_yellow:
                raise ValueError(
                    "Minimum conflicting intergreen time "
                    f"({np.min(conflicting_intergreens)}s) "
                    "cannot be lower than the default yellow "
                    f"time ({default_yellow}s)."
                )

        self._current_group_states = ["r"] * self._num_groups

        # How long to remain yellow.
        self._yellow_timers = np.zeros(self._num_groups)

        # How long to remain not green.
        self._lockout_timers = np.zeros(self._num_groups)

        # Numpy matrix representing all possible phases the controller can have.
        self._phases = self._get_possible_phases()

    @property
    def phase_count(self) -> int:
        return self._phases.shape[0]

    def step(self, new_phase_idx: int) -> str:
        """Advance controller by one time step.

        Args:
            new_phase: New phase which the controller tries to reach.
                This doesn't need to change between steps.

        Returns:
            SUMO signal group state string.
        """
        new_phase = self._phases[new_phase_idx]

        # Green -> Red transitions.
        for i in range(self._num_groups):
            # If group is currently green, but needs
            # to be turned red, it will turn yellow.
            if self._current_group_states[i] == "g" and new_phase[i] == 0:
                self._current_group_states[i] = "y"
                self._yellow_timers[i] = self._default_yellow

                # Set lockout times for conflicting groups.
                for j in range(self._num_groups):
                    if i != j and self._intergreens[i, j] > 0:
                        self._lockout_timers[j] = max(
                            self._lockout_timers[j], self._intergreens[i, j]
                        )

        # Yellow -> Red transitions and lockout timings.
        for i in range(self._num_groups):
            # Advance groups yellow timer.
            if self._yellow_timers[i] > 0:
                self._yellow_timers[i] = max(
                    0.0, self._yellow_timers[i] - self._delta_t
                )
                # If yellow expires and group needs to turn red, it will turn red.
                if self._yellow_timers[i] <= 0.0 and new_phase[i] == 0:
                    self._current_group_states[i] = "r"

            # Advance groups lockout timer.
            if self._lockout_timers[i] > 0:
                self._lockout_timers[i] = max(
                    0.0, self._lockout_timers[i] - self._delta_t
                )

        # Red -> Green transitions.
        for j in range(self._num_groups):
            if new_phase[j] == 1:
                # If group needs to be green but currently
                # isn't, it will try to transition.
                if self._current_group_states[j] != "g":
                    # Check if any conflicting groups are green or yellow.
                    conflict_active = False
                    for i in range(self._num_groups):
                        # If the groups have a conflict and the i group
                        # is currently active, conflict active is True.
                        if self._intergreens[i, j] > 0 and (
                            self._current_group_states[i] in ["g", "y"]
                        ):
                            conflict_active = True
                            break

                    # If group doesn't to wait for lockout and no
                    # conflict groups are active, it will turn green.
                    if self._lockout_timers[j] <= 0 and not conflict_active:
                        self._current_group_states[j] = "g"
                        self._yellow_timers[j] = 0.0

        return "".join(self._current_group_states)

    def _get_possible_phases(self) -> np.ndarray:
        """Get all possible phases based on the intergreen matrix.

        Args:
            intergreens: Intergreen times as a matrix. Each row represents an
                origin group and each column the target group. Each element is
                the shortest time between the origin and target group.

        Returns:
            List of possible phases as a 2D matrix. 1 means green and 0 means red.
        """
        num_groups = self._intergreens.shape[0]

        # Groups conflict if either origin->target or
        # target->origin requires intergreen time > 0.
        conflict_matrix = (self._intergreens > 0) | (self._intergreens.T > 0)

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
