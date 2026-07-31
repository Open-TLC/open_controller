from abc import ABC, abstractmethod

import libsumo

from .area_detector import AreaDetector, TransitAreaDetector
from .point_detector import TRANSIT_VEHICLE_TYPES


class BaseE2AreaDetector(AreaDetector, ABC):
    """Shared implementation layer for all SUMO E2-based area detectors."""

    def __init__(self, detector_id: str) -> None:
        super().__init__()
        self._id = detector_id
        self._vehicle_count: float = 0.0
        self._average_speed: float = 0.0
        self._average_time_loss: float = 0.0

    @property
    def id(self) -> str:
        """ID of the detector."""
        return self._id

    def tick(self) -> None:
        """Update the detectors internal state."""
        raw_count, raw_speed, raw_loss = self._fetch_metrics()

        self._vehicle_count = float(raw_count)
        self._average_speed = max(0.0, float(raw_speed))
        self._average_time_loss = max(0.0, float(raw_loss))

    @property
    def vehicle_count(self) -> float:
        """Total number or vehicles currently in the area."""
        return self._vehicle_count

    @property
    def average_speed(self) -> float:
        """Average speed (m/s) of a vehicle currently in the area."""
        return self._average_speed

    @property
    def average_time_loss(self) -> float:
        """Average time loss (s) experienced by vehicles in the area."""
        return self._average_time_loss

    @abstractmethod
    def _fetch_metrics(self) -> tuple[float, float, float]:
        """Get readings from the detector.

        Returns:
            Vehicle count, average speed, and average time loss.

        """
        ...


class E2AreaDetector(BaseE2AreaDetector):
    """AreaDetector implementation using SUMO's E2 detector."""

    def _fetch_metrics(self) -> tuple[float, float, float]:
        count = libsumo.lanearea.getLastStepVehicleNumber(self._id)
        speed = libsumo.lanearea.getLastStepMeanSpeed(self._id)
        loss = libsumo.lanearea.getLastIntervalMeanTimeLoss(self._id)
        return count, speed, loss


class E2TransitAreaDetector(BaseE2AreaDetector, TransitAreaDetector):
    """AreaDetector implementation using SUMO's E2 detector for transit only."""

    def __init__(self, detector_id: str) -> None:
        super().__init__(detector_id)
        # ID needs to be overridden to differentiate transit detector from possible
        # general detector that uses the same SUMO detector. This makes it possible
        # to re-use SUMO detectors across logical detectors.
        self._id = f"transit_{detector_id}"
        self._sumo_id = detector_id

    def _fetch_metrics(self) -> tuple[float, float, float]:
        vehicle_ids = libsumo.lanearea.getLastStepVehicleIDs(self._sumo_id)
        transit_ids = [
            v
            for v in vehicle_ids
            if libsumo.vehicle.getTypeID(v) in TRANSIT_VEHICLE_TYPES
        ]

        count = len(transit_ids)
        if count > 0:
            speed = sum(libsumo.vehicle.getSpeed(v) for v in transit_ids) / count
            loss = sum(libsumo.vehicle.getTimeLoss(v) for v in transit_ids) / count
        else:
            # If no transit vehicles are detected, values signal no readings.
            speed, loss = -1.0, -1.0

        return count, speed, loss
