import numpy as np


class SafetyController:
    """Manage traffic light transitions, clearance periods, and safety lockouts."""

    def __init__(
        self,
        intergreens: np.ndarray,
        step_length: float,
        default_yellow: float = 3.0,
    ) -> None:
        """Create safety controller from junction geometry and timing options.

        Args:
            intergreens: N x N matrix of transition times between links.
            step_length: Length of a time step in seconds.
            default_yellow: Length of yellow light.

        """
        self._intergreens = intergreens
        self._delta_t = step_length
        self._default_yellow = default_yellow

        # The dimension 'N' is now the sum of vehicle links and pedestrian crossings
        self._num_elements = intergreens.shape[0]
        self._current_states = ["r"] * self._num_elements
        self._yellow_timers = np.zeros(self._num_elements)
        self._lockout_timers = np.zeros(self._num_elements)

        self._phases = self._get_possible_phases()

    @property
    def phase_count(self) -> int:
        return self._phases.shape[0]

    def step(self, new_phase_idx: int) -> str:
        """Advance the safety controller by one time-step.

        Args:
            new_phase_idx: Index of the target maximal phase to transition to.

        Returns:
            A string of states representing the physical SUMO light states.

        """
        new_phase = self._phases[new_phase_idx]

        # Green -> Yellow transitions.
        for i in range(self._num_elements):
            if self._current_states[i] == "g" and new_phase[i] == 0:
                self._current_states[i] = "y"
                self._yellow_timers[i] = self._default_yellow

                for j in range(self._num_elements):
                    if i != j and self._intergreens[i, j] > 0:
                        self._lockout_timers[j] = max(
                            self._lockout_timers[j],
                            self._intergreens[i, j],
                        )

        # Yellow -> Red transitions.
        for i in range(self._num_elements):
            if self._current_states[i] == "y" and self._yellow_timers[i] <= 0.0:
                self._current_states[i] = "r"

        # Red -> Green transitions.
        for i in range(self._num_elements):
            if new_phase[i] == 1 and self._current_states[i] != "g":
                conflict_active = False
                for j in range(self._num_elements):
                    if self._intergreens[j, i] > 0 and self._current_states[j] in [
                        "g",
                        "y",
                    ]:
                        conflict_active = True
                        break

                if self._lockout_timers[i] <= 0.0 and not conflict_active:
                    self._current_states[i] = "g"

        # Advance all yellow and lockout timers.
        for i in range(self._num_elements):
            if self._yellow_timers[i] > 0.0:
                self._yellow_timers[i] = max(
                    0.0,
                    self._yellow_timers[i] - self._delta_t,
                )
            if self._lockout_timers[i] > 0.0:
                self._lockout_timers[i] = max(
                    0.0,
                    self._lockout_timers[i] - self._delta_t,
                )

        return "".join(self._current_states)

    def _get_possible_phases(self) -> np.ndarray:
        """Generate all possible phases.

        Returns all maximal phases and an all-red phase.
        """
        num_elements = self._num_elements

        # Build a symmetric adjacency/conflict representation
        conflict_matrix = (self._intergreens > 0) | (self._intergreens.T > 0)
        np.fill_diagonal(conflict_matrix, False)

        # Build complement graph adjacency masks where:
        # a '1' at bit 'j' in adj[i] means element 'i' and 'j' DO NOT conflict.
        adj = [0] * num_elements
        for i in range(num_elements):
            mask = 0
            for j in range(num_elements):
                if i != j and not conflict_matrix[i, j]:
                    mask |= 1 << j
            adj[i] = mask

        maximal_phases_masks = []

        # Bitwise Bron-Kerbosch recursion to find maximal cliques
        def bk(r: int, p: int, x: int):
            if p == 0 and x == 0:
                maximal_phases_masks.append(r)
                return

            pivot_k = p | x
            pivot = (pivot_k & -pivot_k).bit_length() - 1
            temp_p = p & ~adj[pivot]

            while temp_p > 0:
                lsb = temp_p & -temp_p
                v = lsb.bit_length() - 1

                bk(r | lsb, p & adj[v], x & adj[v])

                p &= ~lsb
                x |= lsb
                temp_p &= ~lsb

        all_nodes_mask = (1 << num_elements) - 1
        bk(0, all_nodes_mask, 0)

        # Here we only keep maximal phases and add the all-red phase (0)
        final_masks = set(maximal_phases_masks)
        final_masks.add(0)

        # Convert the masks back to 2D numpy arrays
        result_list = [
            [(mask >> i) & 1 for i in range(num_elements)] for mask in final_masks
        ]

        return np.unique(np.array(result_list, dtype=int), axis=0)
