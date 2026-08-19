import time
import unittest

from services.control_engine.src.detectors.dummy_point_detector import (
    DummyPointDetector,
)
from services.control_engine.src.configuration import TimerConf
from services.control_engine.src.extender import GapSeekingExtender

from services.control_engine.src.timer import Timer

MULTIPLIER = 1000


class TestGapSeekingExtender(unittest.TestCase):
    def test_extension(self):
        params = {
            "timer_mode": "real",
            "time_step": 0.1,
            "real_time_multiplier": MULTIPLIER,
        }
        conf = TimerConf(params)

        timer = Timer(conf)

        detector = DummyPointDetector(timer)

        options = {"detector": "dummy", "gap": 0.5}
        extender = GapSeekingExtender()
