from collections.abc import Callable
from typing import Any

from services.control_engine.src.detectors.area_detector import AreaDetector
from services.control_engine.src.detectors.point_detector import PointDetector

from .requester import Requester


class TriggerRequester(Requester):
    """Requester that starts requesting on detection and ends once the group is served.

    Requst starts when any of the detectors detects a vehicle and ends once the main
    group has received green signal.
    """

    def __init__(
        self,
        requester_id: str,
        raw_options: dict[str, Any],
        get_group_is_green_cb: Callable[[], bool],
        detectors: list[AreaDetector | PointDetector],
    ) -> None:
        self._id: str = requester_id
        self._is_requesting: bool = False
        self._get_group_is_green = get_group_is_green_cb

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

        found_ids: set[str] = set()
        for detector in detectors:
            det_id_str = str(detector.id)
            if det_id_str not in target_ids:
                continue

            found_ids.add(det_id_str)
            if isinstance(detector, AreaDetector):
                self._area_detectors.append(detector)
            elif isinstance(detector, PointDetector):
                self._point_detectors.append(detector)

        missing_ids = target_ids - found_ids
        if missing_ids:
            raise ValueError(
                f"Requester {requester_id} referenced non-existent detector "
                f"IDs: {missing_ids}",
            )

    @property
    def id(self) -> str:
        """Get ID of the requester."""
        return self._id

    def tick(self) -> None:
        """Update requesting status based on detector states."""
        # If any detector has vehicles, the request is turned on.
        if any(detector.vehicle_count > 0 for detector in self._area_detectors) or any(
            detector.is_occupied for detector in self._point_detectors
        ):
            self._is_requesting = True
            return

        # If no vehicles are currently detected but a request is active,
        # hold the request until the green signal is served.
        if self._is_requesting and self._get_group_is_green():
            self._is_requesting = False

    @property
    def is_requesting(self) -> bool:
        """Check if green request is active."""
        return self._is_requesting
