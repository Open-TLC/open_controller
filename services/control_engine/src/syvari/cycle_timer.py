from typing import Any

from services.control_engine.src.timer import Timer


class CycleTimer(Timer):
    """Cyclical timer.

    Cycle timer makes it possible to keep track of the current
    cycle phase across multiple connected controllers.
    """

    def __init__(self, timer_prm: dict[str, Any], cycle_length: float):
        """Create cycle timer.

        Args:
            timer_prm: Dictionary of Timer object parameters.
            cycle_length: The length of a single cycle in seconds.

        """
        super().__init__(timer_prm)
        self._cycle_length: float = cycle_length

    @property
    def cycle_phase(self) -> float:
        """Current phase of the cycle.

        Returns:
            float: Time since the last cycle start in seconds.

        """
        return self.seconds % self._cycle_length

    @property
    def cycle_length(self) -> float:
        """Length of the cycle (s)."""
        return self._cycle_length
