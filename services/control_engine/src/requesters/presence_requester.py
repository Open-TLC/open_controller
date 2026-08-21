from typing import Any

from services.control_engine.src.detectors.area_detector import AreaDetector
from services.control_engine.src.detectors.point_detector import PointDetector

from .requester import Requester


class PresenceRequester(Requester):
    """Requester with no memory.

    Requests green, if any of its detectors detect a vehicle.
    """

    def __init__(
        self,
        requester_id: str,
        raw_options: dict[str, Any],
        detectors: list[AreaDetector | PointDetector],
    ) -> None:
        self._id: str = requester_id
        self._is_requesting: bool = False

        detector_ids = raw_options.get("detectors")
        if (
            detector_ids is None
            or type(detector_ids) is not list
            or len(detector_ids) == 0
        ):
            raise ValueError(f"No detectors configured for requester {requester_id}")

        target_ids = {str(det_id) for det_id in detector_ids}
        self._point_detectors: list[PointDetector] = []
        self._area_detectors: list[AreaDetector] = []

        for detector in detectors:
            if detector.id not in target_ids:
                continue

            if isinstance(detector, AreaDetector):
                self._area_detectors.append(detector)
            elif isinstance(detector, PointDetector):
                self._point_detectors.append(detector)

    @property
    def id(self) -> str:
        """Get ID of the requester."""
        return self._id

    def tick(self) -> None:
        """Update requesting status based on detector states."""
        # If any detector has vehicles, request is turned on.
        if any(detector.vehicle_count > 0 for detector in self._area_detectors):
            self._is_requesting = True
            return

        if any(detector.is_occupied for detector in self._point_detectors):
            self._is_requesting = True
            return

        # If none of the detectors have vehicles, turn off request.
        self._is_requesting = False

    @property
    def is_requesting(self) -> bool:
        """Check if green request is active."""
        return self._is_requesting
