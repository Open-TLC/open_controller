import libsumo

from .area_detector import AreaDetector


class E2AreaDetector(AreaDetector):
    def __init__(self, detector_id: str) -> None:
        super().__init__()

        self._id = detector_id

    def vehicle_count(self) -> float:
        return float(libsumo.lanearea.getLastStepVehicleNumber(self._id))

    def average_speed(self) -> float:
        speed = float(libsumo.lanearea.getLastStepMeanSpeed(self._id))
        return max(0.0, speed)

    def average_time_loss(self) -> float:
        loss = float(libsumo.lanearea.getLastIntervalMeanTimeLoss(self._id))
        return max(0.0, loss)
