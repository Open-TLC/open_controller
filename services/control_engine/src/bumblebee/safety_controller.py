import numpy as np


class SafetyController:
    def __init__(
        self,
        logical_intergreens: np.ndarray,
        link_to_logical_map: list[int],
        step_length: float,
        default_yellow: float = 3.0,
    ) -> None:
        """Args:
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
                            self._lockout_timers[j],
                            self._intergreens[i, j],
                        )

        # Yellow -> Red transitions and lockout timings.
        for i in range(self._num_logical):
            if self._yellow_timers[i] > 0:
                self._yellow_timers[i] = max(
                    0.0,
                    self._yellow_timers[i] - self._delta_t,
                )

            if self._current_group_states[i] == "y" and self._yellow_timers[i] <= 0.0:
                if new_phase[i] == 0:
                    self._current_group_states[i] = "r"

            if self._lockout_timers[i] > 0:
                self._lockout_timers[i] = max(
                    0.0,
                    self._lockout_timers[i] - self._delta_t,
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
        num_logical = self._num_logical

        conflict_matrix = (self._intergreens > 0) | (self._intergreens.T > 0)
        np.fill_diagonal(conflict_matrix, False)

        # 2. Build adjacency for the COMPLEMENT graph using bitmasks.
        # If a bit is 1, it means there is NO conflict between the two signals.
        adj = [0] * num_logical
        for i in range(num_logical):
            mask = 0
            for j in range(num_logical):
                if i != j and not conflict_matrix[i, j]:
                    mask |= 1 << j
            adj[i] = mask

        maximal_phases_masks = []

        # 3. Bitwise Bron-Kerbosch Algorithm
        def bk(r: int, p: int, x: int):
            # If P and X are empty, R is a maximal independent set
            if p == 0 and x == 0:
                maximal_phases_masks.append(r)
                return

            # Pivot optimization: pick an arbitrary node from P union X
            # This drastically reduces the number of recursive branches
            pivot_k = p | x
            pivot = (pivot_k & -pivot_k).bit_length() - 1

            # Only iterate over nodes in P that are NOT connected to the pivot
            temp_p = p & ~adj[pivot]

            while temp_p > 0:
                # Get the least significant set bit (the node 'v')
                lsb = temp_p & -temp_p
                v = lsb.bit_length() - 1

                # Recurse: add 'v' to R, restrict P and X to neighbors of 'v'
                bk(r | lsb, p & adj[v], x & adj[v])

                # Move 'v' from P to X
                p &= ~lsb
                x |= lsb
                temp_p &= ~lsb

        # Start BK with all nodes available in P (all bits set to 1)
        all_nodes_mask = (1 << num_logical) - 1
        bk(0, all_nodes_mask, 0)

        # 4. Add single phases and all-red, using a set to automatically deduplicate
        final_masks = set(maximal_phases_masks)

        for i in range(num_logical):
            final_masks.add(1 << i)  # Single group
        final_masks.add(0)  # All red phase

        # 5. Convert bitmasks back to a 2D numpy array
        result_list = [
            [(mask >> i) & 1 for i in range(num_logical)] for mask in final_masks
        ]

        # np.unique sorts the array and provides your consistent, clean output
        return np.unique(np.array(result_list, dtype=int), axis=0)
