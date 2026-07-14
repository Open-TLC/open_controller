"""The timer.

This module implements system timer for clockwork_tc
"""

# Coopyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#
import time


class Timer:
    """Timer for handling time steps and conversions."""

    def __init__(self, timer_prm):
        self.time_step = timer_prm["time_step"]
        self._time_multiplier = timer_prm["real_time_multiplier"]
        self.start_rtime = time.time()
        self._cur_rtime = time.time()
        self.steps = 0
        self.last_update = self._cur_rtime
        # This is used to compensate for the time drift as integrator
        self.aggregate_time_drift = 0.0

    def __str__(self):
        return f"Timer, {self.steps} steps and {self.seconds} seconds"

    def reset(self):
        """Start the timer from zero."""
        self.steps = 0
        self.start_rtime = time.time()
        self._cur_rtime = time.time() - self.start_rtime

    def tick(self):
        """One time step forward."""
        self.steps += 1
        self._cur_rtime = (time.time() - self.start_rtime) * self._time_multiplier
        self.aggregate_time_drift += self._get_time_since_last_update() - self.time_step

    def sleep_tick(self):
        """Sleep for one tick.

        This advances the internal clock of the timer.
        """
        self._cur_rtime = (time.time() - self.start_rtime) * self._time_multiplier

    def _get_time_since_last_update(self) -> float:
        """Get the last update time and updates the counter to current time."""
        last_update_before_reset = self.last_update
        self.last_update = time.time()
        return self.last_update - last_update_before_reset

    def reset_time_step(self) -> None:
        """Reset the aggregate time drift.

        This is called by the controller after it starts again after stopping
        (by the UI)
        """
        self.aggregate_time_drift = 0.0
        self.last_update = time.time()

    def get_next_time_step(self) -> float:
        """Next time step in seconds."""
        # We compensate the time step with the aggregate time drift
        # This works as an integrator and adjusts the time step to match the real time
        next_corrected_time_step = self.time_step - self.aggregate_time_drift
        return max(next_corrected_time_step, 0.0)

    def str_seconds(self) -> str:
        """Real time in seconds in string format."""
        return str(round(self.steps / 10, 1))

    @property
    def seconds(self) -> float:
        """Time in seconds, rounded up to three decimals."""
        return round(self.steps * self.time_step, 5)

    @property
    def real_seconds(self) -> float:
        """Real time in seconds from simulation start."""
        return round(self._cur_rtime, 5)

    @seconds.setter
    def seconds(self, new_seconds: float) -> None:
        # Sets _steps_ to closest second value
        self.steps = round(
            new_seconds / self.time_step,
            5,
        )  # one might consider flooring?
