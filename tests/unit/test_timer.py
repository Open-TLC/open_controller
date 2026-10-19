import time
import unittest

from services.control_engine.src.configuration import TimerConf
from services.control_engine.src.timer import Timer

# Kept low enough that each step is several ms of wall time: sleep() costs
# about 1 ms in Docker Desktop containers, so faster steps can't be timed there.
MULTIPLIER = 10


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
        for _ in range(300):
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

    def test_timer_resumes_normal_speed_after_pause(self) -> None:
        params = {
            "timer_mode": "real",
            "time_step": 0.1,
            "real_time_multiplier": 10,
        }
        timer = Timer(TimerConf(params))
        timer.reset()
        step_wall_time = 0.1 / 10

        for _ in range(20):
            time.sleep(timer.wall_time_to_next_step())
            timer.tick()

        # Pause, e.g. the simulation was halted in sumo-gui.
        time.sleep(0.5)

        start_real = time.monotonic()
        for _ in range(20):
            time.sleep(timer.wall_time_to_next_step())
            timer.tick()
        per_step = (time.monotonic() - start_real) / 20

        # Without re-anchoring the timer would rush through the 50 missed steps.
        self.assertGreater(
            per_step,
            0.8 * step_wall_time,
            msg=f"Timer rushed after pause: {per_step * 1000:.2f} ms per step,"
            f" expected about {step_wall_time * 1000:.2f} ms",
        )
