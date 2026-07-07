from .area_detector import AreaDetector


class FusedAreaDetector(AreaDetector):
    """Combine the readings of two area detectors to improve reading accuracy."""

    def __init__(self, det_a: AreaDetector, det_b: AreaDetector) -> None:
        super().__init__()

        self._det_a = det_a
        self._det_b = det_b

    def tick(self) -> None:
        """Update states of both child detectors."""
        self._det_a.tick()
        self._det_b.tick()

    @property
    def vehicle_count(self) -> float:
        """Total number of vehicles currently in detection area."""
        return (self._det_a.vehicle_count + self._det_b.vehicle_count) / 2

    @property
    def average_speed(self) -> float:
        """Average speed (m/s) of vehicles in the detection area."""
        return (self._det_a.average_speed + self._det_b.average_speed) / 2

    @property
    def average_time_loss(self) -> float:
        """Average time loss (s) of vehicles in the detection area."""
        return (self._det_a.average_time_loss + self._det_b.average_time_loss) / 2
