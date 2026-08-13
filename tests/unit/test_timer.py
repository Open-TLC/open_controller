import time
import unittest

from services.control_engine.src.configuration import TimerConf
from services.control_engine.src.timer import Timer

MULTIPLIER = 1000


class TestTimer(unittest.TestCase):
    def _create_timer(self) -> Timer:
        params = {
            "timer_mode": "real",
            "time_step": 0.1,
            "real_time_multiplier": MULTIPLIER,
        }
        conf = TimerConf(params)
        return Timer(conf)

    def test_timer_drift(self) -> None:
        timer = self._create_timer()
        timer.reset()

        start_timer = timer.seconds
        start_real = time.monotonic()
        for _ in range(10_000):
            timer.tick()
            time.sleep(timer.wall_time_to_next_step())

        end_real = time.monotonic()
        end_timer = timer.seconds

        elapsed_timer = end_timer - start_timer
        elapsed_real = (end_real - start_real) * MULTIPLIER

        timer_drift = abs(elapsed_timer - elapsed_real)

        self.assertLessEqual(
            timer_drift,
            0.1,
            msg=f"Timer drifted by {timer_drift:.4f}s (Simulated: {elapsed_timer:.2f}s,"
            f" Real: {elapsed_real:.2f}s)",
        )
