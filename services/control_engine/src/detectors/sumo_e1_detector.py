from abc import ABC, abstractmethod

import libsumo

from .point_detector import TRANSIT_VEHICLE_TYPES, PointDetector, TransitPointDetector


class BaseE1Detector(PointDetector, ABC):
    """Shared implementation layer for all SUMO E1-based detectors."""

    def __init__(self, detector_id: str) -> None:
        super().__init__()
        self._id = detector_id
        self._current_time: float = 0
        self._occupied: bool = False
        self._detection_start: float = -1

    @property
    def id(self) -> str:
        """ID of the detector."""
        return self._id

    def tick(self) -> None:
        """Update the detector."""
        self._current_time = libsumo.simulation.getTime()

        # Defer the specific occupancy rule to the subclass
        currently_occupied = self._check_occupancy()

        if not self._occupied and currently_occupied:
            self._occupied = True
            self._detection_start = self._current_time
        elif self._occupied and not currently_occupied:
            self._occupied = False
            self._detection_start = -1

    @property
    def is_occupied(self) -> bool:
        """True if detector currently has a vehicle detected."""
        return self._occupied

    @property
    def detection_duration(self) -> float:
        """Duration of the current detection in seconds."""
        if not self._occupied:
            return 0.0
        return self._current_time - self._detection_start

    @abstractmethod
    def _check_occupancy(self) -> bool: ...


class E1PointDetector(BaseE1Detector):
    """Point detector implementation using SUMO's E1 detector."""

    def _check_occupancy(self) -> bool:
        return libsumo.inductionloop.getLastStepVehicleNumber(self._id) > 0


class E1TransitPointDetector(BaseE1Detector, TransitPointDetector):
    """Transit point detector using SUMO's E1 detector."""

    def __init__(self, detector_id: str) -> None:
        super().__init__(detector_id)
        # ID needs to be overridden to differentiate transit detector from possible
        # general detector that uses the same SUMO detector. This makes it possible
        # to re-use SUMO detectors across logical detectors.
        self._id = f"transit_{detector_id}"
        self._sumo_id = detector_id

    def _check_occupancy(self) -> bool:
        vehicle_data = libsumo.inductionloop.getVehicleData(self._sumo_id)
        return any(
            vType in TRANSIT_VEHICLE_TYPES for (_, _, _, _, vType) in vehicle_data
        )
