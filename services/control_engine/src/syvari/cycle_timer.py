from src.timer import Timer


class CycleTimer(Timer):
    """
    CycleTimer is a cyclical timer that makes it possible to keep track
    of the current cycle phase across multiple connected controllers.
    """

    def __init__(self, timer_prm, cycle_length: float):
        """
        Args:
            timer_prm: Dictionary of Timer object parameters.
            cycle_length: The length of a single cycle in seconds.
        """
        super().__init__(timer_prm)
        self._cycle_length: float = cycle_length

    @property
    def cycle_phase(self) -> float:
        """
        Current phase of the cycle.

        Returns:
            float: Time since the last cycle start in seconds.
        """
        return self.seconds % self._cycle_length

    @property
    def cycle_length(self) -> float:
        return self._cycle_length
