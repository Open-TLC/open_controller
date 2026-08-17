"""Timer module for handling clock synchronization."""

# Coopyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved

import logging
import time

from .configuration import TimerConf

logger = logging.getLogger(__name__)


class Timer:
    """Timer for handling time steps and real-time synchronization."""

    def __init__(self, conf: TimerConf, warnings: bool = False) -> None:
        self._step_length: float = conf.time_step
        self._time_multiplier: float = conf.real_time_multiplier
        self._mode: str = conf.mode

        self._target_wall_interval = self._step_length / self._time_multiplier

        self._do_warnings = warnings

        self._steps: int = 0
        self._start_wall_time: float = time.monotonic()

    @property
    def seconds(self) -> float:
        """Simulation time in seconds."""
        return self._steps * self._step_length

    @property
    def steps(self) -> int:
        """Number of steps taken."""
        return self._steps

    @property
    def step_length(self) -> float:
        """Length of a step in seconds."""
        return self._step_length

    def reset(self) -> None:
        """Start the timer from zero."""
        self._steps = 0
        self._start_wall_time = time.monotonic()

    def tick(self) -> None:
        """Advance simulation by one step."""
        self._steps += 1

    def wall_time_to_next_step(self) -> float:
        """Wall-clock time (in seconds) to wait until the next step."""
        # Fixed timer runs as fast as possible. Should be used only in synchronized
        # operations.
        if self._mode == "fixed":
            return 0

        # The time it should have taken to complete current steps.
        expected_wall_time = self._start_wall_time + (
            self._steps * self._target_wall_interval
        )

        now = time.monotonic()
        diff = expected_wall_time - now

        if diff < 0 and self._do_warnings:
            logger.warning(
                "Can't keep up. Timer is running %.3fs behind timer at step %d.",
                -diff,
                self._steps,
            )

        return max(0.0, diff)

    def __str__(self) -> str:
        """Timer as a human-readable string."""
        return f"Timer, {self._steps} steps and {round(self.seconds, 2)} seconds"
