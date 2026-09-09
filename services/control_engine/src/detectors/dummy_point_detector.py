from services.control_engine.src.timer import Timer

from .point_detector import PointDetector


class DummyPointDetector(PointDetector):
    def __init__(self, timer: Timer):
        self._timer = timer
        self._id = "dummy"
        self._is_occupied = False

    @property
    def id(self) -> str:
        return self._id

    @property
    def is_occupied(self) -> bool:
        return self._is_occupied

    def tick(self) -> None:
        if not self._is_occupied:
            self._detection_start = self._timer.seconds
        elif self._is_occupied:
            self._detection_start = None

    @property
    def detection_duration(self) -> float:
        if not self._is_occupied or self._detection_start is None:
            return 0.0
        return self._timer.seconds - self._detection_start
