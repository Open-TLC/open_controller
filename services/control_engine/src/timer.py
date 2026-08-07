"""The timer.

This module implements system timer for clockwork_tc
"""

# Coopyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#
import time

from .configuration import TimerConf

# Alias for performance gains.
_get_clock = time.perf_counter


class Timer:
    """Timer for handling time steps and conversions."""

    def __init__(self, conf: TimerConf) -> None:
        self.time_step: float = conf.time_step
        self._time_multiplier: float = conf.real_time_multiplier
        now: float = _get_clock()
        self.start_rtime: float = now
        self._cur_rtime: float = 0.0
        self.steps: int = 0
        self.last_update: float = now

        # This is used to compensate for the time drift as integrator
        self.aggregate_time_drift: float = 0.0

    def __str__(self) -> str:
        """Timer as human readable string."""
        return f"Timer, {self.steps} steps and {round(self.seconds, 5)} seconds"

    def reset(self) -> None:
        """Start the timer to zero."""
        self.steps = 0
        now: float = _get_clock()
        self.start_rtime = now
        self._cur_rtime = 0.0
        self.last_update = now
        self.aggregate_time_drift = 0.0

    def tick(self) -> None:
        """One time step forward."""
        self.steps += 1
        now: float = _get_clock()
        # Single clock read updates both real-time state and aggregate time drift
        self._cur_rtime = (now - self.start_rtime) * self._time_multiplier
        self.aggregate_time_drift += (now - self.last_update) - self.time_step
        self.last_update = now

    def sleep_tick(self) -> None:
        """Sleep for one tick.

        This advances the internal clock of the timer.
        """
        self._cur_rtime = (_get_clock() - self.start_rtime) * self._time_multiplier

    def _get_time_since_last_update(self) -> float:
        """Get the last update time and updates the counter to current time."""
        now: float = _get_clock()
        last_update_diff: float = now - self.last_update
        self.last_update = now
        return last_update_diff

    def reset_time_step(self) -> None:
        """Reset the aggregate time drift.

        This is called by the controller after it starts again after stopping
        (by the UI)
        """
        self.aggregate_time_drift = 0.0
        self.last_update = _get_clock()

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
        """Time in seconds."""
        return self.steps * self.time_step

    @property
    def real_seconds(self) -> float:
        """Real time in seconds from simulation start."""
        return self._cur_rtime

    @seconds.setter
    def seconds(self, new_seconds: float) -> None:
        # Sets steps to closest step count for given second value
        self.steps = round(new_seconds / self.time_step)
