import libsumo

from .area_detector import AreaDetector


class E3AreaDetector(AreaDetector):
    """AreaDetector implementation using SUMO's E3 detector."""

    def __init__(self, detector_id: str) -> None:
        super().__init__()

        self._id = detector_id

        self._vehicle_count: float = 0.0
        self._average_speed: float = 0.0
        self._average_time_loss: float = 0.0

    def tick(self) -> None:
        """Update detections from simulation."""
        self._vehicle_count = float(
            libsumo.multientryexit.getLastStepVehicleNumber(self._id),
        )

        raw_speed = float(libsumo.multientryexit.getLastStepMeanSpeed(self._id))
        self._average_speed = max(0.0, raw_speed)

        raw_time_loss = float(
            libsumo.multientryexit.getLastIntervalMeanTimeLoss(self._id),
        )
        self._average_time_loss = max(0.0, raw_time_loss)

    @property
    def vehicle_count(self) -> float:
        """Total number of vehicles currently in detection area."""
        return self._vehicle_count

    @property
    def average_speed(self) -> float:
        """Average speed (m/s) of vehicles in the detection area."""
        return self._average_speed

    @property
    def average_time_loss(self) -> float:
        """Average time loss (s) of vehicles in the detection area."""
        return self._average_time_loss
