import unittest

from services.control_engine.src.configuration import TimerConf
from services.control_engine.src.detectors.dummy_point_detector import (
    DummyPointDetector,
)
from services.control_engine.src.extenders.gap_seeking_extender import (
    GapSeekingExtender,
)
from services.control_engine.src.timer import Timer

MULTIPLIER = 1000


class TestGapSeekingExtender(unittest.TestCase):
    def test_extension(self):
        params = {
            "mode": "real",
            "time_step": 0.1,
            "real_time_multiplier": MULTIPLIER,
        }
        conf = TimerConf(params)

        timer = Timer(conf)

        options = {"detector": "dummy", "gap": 0.5}

        detector = DummyPointDetector(timer)

        extender = GapSeekingExtender("test", timer, options, [detector])

        # Extender should start as not extending.
        self.assertEqual(extender.is_extending, False)

        # Turn on detector and update everything.
        detector._is_occupied = True

        timer.tick()
        detector.tick()
        extender.tick()

        # Extender should now extend.
        self.assertEqual(extender.is_extending, True)

        # Turn off detector and update everything.
        detector._is_occupied = False

        timer.tick()
        detector.tick()
        extender.tick()

        # Extender should extend for 0.5 seconds after detection stops.
        # Remaining: 0.5 s
        self.assertEqual(extender.is_extending, True)

        timer.tick()
        detector.tick()
        extender.tick()

        # Remaining: 0.4 s
        self.assertEqual(extender.is_extending, True)

        timer.tick()
        detector.tick()
        extender.tick()

        # Remaining: 0.3 s
        self.assertEqual(extender.is_extending, True)

        timer.tick()
        detector.tick()
        extender.tick()

        # Remaining: 0.2 s
        self.assertEqual(extender.is_extending, True)

        timer.tick()
        detector.tick()
        extender.tick()

        # Remaining: 0.1 s
        self.assertEqual(extender.is_extending, True)

        timer.tick()
        detector.tick()
        extender.tick()

        # Remaining: 0.0 s
        # Extension ends.
        self.assertEqual(extender.is_extending, False)

        # Detector is turned back on.
        detector._is_occupied = True

        timer.tick()
        detector.tick()
        extender.tick()

        # Extension should start again.
        self.assertEqual(extender.is_extending, True)
