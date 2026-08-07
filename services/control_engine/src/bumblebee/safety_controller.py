import numpy as np

from services.control_engine.src.geometry.junction_geometry import JunctionGeometry
from services.control_engine.src.timer import Timer


class SafetyController:
    """Manage traffic light transitions, clearance periods, and safety lockouts."""

    def __init__(
        self,
        intergreens: np.ndarray,
        geometry: JunctionGeometry,
        timer: Timer,
        default_yellow: float = 3.0,
    ) -> None:
        """Create safety controller from junction geometry and timing options.

        Args:
            intergreens: N x N matrix of transition times between links.
            geometry: Description of junctions geometry.
            timer: Timer used to calculate safety timings.
            default_yellow: Length of yellow light.

        """
        self._intergreens = intergreens
        self._geometry = geometry
        self._default_yellow = default_yellow

        self._timer = timer
        self._last_updated = self._timer.seconds

        # The dimension 'N' is now the sum of vehicle links and pedestrian crossings
        self._num_elements = intergreens.shape[0]
        self._current_states = ["r"] * self._num_elements
        self._yellow_timers: np.ndarray = np.zeros(self._num_elements)
        self._lockout_timers: np.ndarray = np.zeros(self._num_elements)

        self._phases = self._geometry.get_possible_phases(min_major_movements=2)

    @property
    def phase_count(self) -> int:
        """Number of phases."""
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
                conflict_active = any(
                    self._intergreens[j, i] > 0
                    and self._current_states[j] in ("g", "y")
                    for j in range(self._num_elements)
                )

                if self._lockout_timers[i] <= 0.0 and not conflict_active:
                    self._current_states[i] = "g"

        # Update yellow and lockout timers.
        self._update_timers()

        return "".join(self._current_states)

    def _update_timers(self) -> None:
        # Time between last update and now.
        delta_t: float = self._timer.seconds - self._last_updated
        self._last_updated = self._timer.seconds

        # Update timings.
        self._yellow_timers = np.clip(
            self._yellow_timers - delta_t,
            a_min=0.0,
            a_max=None,
        )
        self._lockout_timers = np.clip(
            self._lockout_timers - delta_t,
            a_min=0.0,
            a_max=None,
        )
