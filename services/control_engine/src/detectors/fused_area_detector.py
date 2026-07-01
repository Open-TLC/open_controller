from .area_detector import AreaDetector


class FusedAreaDetector(AreaDetector):
    """Combine the readings of two area detectors into one to improve reading accuracy."""

    def __init__(self, det_a: AreaDetector, det_b: AreaDetector) -> None:
        super().__init__()

        self._det_a = det_a
        self._det_b = det_b

    def vehicle_count(self) -> float:
        return (self._det_a.vehicle_count() + self._det_b.vehicle_count()) / 2

    def average_speed(self) -> float:
        return (self._det_a.average_speed() + self._det_b.average_speed()) / 2

    def average_time_loss(self) -> float:
        return (self._det_a.average_time_loss() + self._det_b.average_time_loss()) / 2
