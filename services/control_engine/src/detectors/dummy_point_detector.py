from .point_detector import PointDetector
from services.control_engine.src.timer import Timer


class DummyPointDetector(PointDetector):
    def __init__(self, timer: Timer):

        self._timer = timer
        self._id = "dummy"
        self._is_occupied = False

    def tick(self) -> None:
        return

    @property
    def id(self) -> str:
        return self._id

    @property
    def is_occupied(self) -> bool:
        return self._is_occupied

    @property
    def detection_duration(self) -> float:
        return 0
