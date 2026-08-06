import numpy as np

from services.control_engine.src.geometry.junction_geometry import JunctionGeometry


class SafetyController:
    """Manage traffic light transitions, clearance periods, and safety lockouts."""

    def __init__(
        self,
        intergreens: np.ndarray,
        geometry: JunctionGeometry,
        step_length: float,
        default_yellow: float = 3.0,
    ) -> None:
        """Create safety controller from junction geometry and timing options.

        Args:
            intergreens: N x N matrix of transition times between links.
            geometry: Description of junctions geometry.
            step_length: Length of a time step in seconds.
            default_yellow: Length of yellow light.

        """
        self._intergreens = intergreens
        self._geometry = geometry
        self._delta_t = step_length
        self._default_yellow = default_yellow

        # The dimension 'N' is now the sum of vehicle links and pedestrian crossings
        self._num_elements = intergreens.shape[0]
        self._current_states = ["r"] * self._num_elements
        self._yellow_timers = np.zeros(self._num_elements)
        self._lockout_timers = np.zeros(self._num_elements)

        self._phases = self._geometry.get_possible_phases(min_major_movements=2)

        # Calculate lane wise phases from link wise phases.
        self._lane_phases = self._geometry.to_lane_wise(self._phases)

    @property
    def phase_count(self) -> int:
        """Number of phases."""
        return self._phases.shape[0]

    @property
    def phases_lane(self) -> np.ndarray:
        """Lane wise phases of the signal controller.

        Matrix of shape (number of phases, number of lanes).
        1 means that lane has green, 0 means that lane has red.
        """
        return self._lane_phases

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

    def get_phase_wise_transit_detections(
        self,
        transit_detections: np.ndarray,
    ) -> np.ndarray:
        """Convert transit detections to phase wise detection matrix."""
        return self.phases_lane @ self._geometry.map_transit_detections_to_lanes(
            transit_detections,
        )
