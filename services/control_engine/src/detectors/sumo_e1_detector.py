import libsumo

from .point_detector import PointDetector


class E1PointDetector(PointDetector):
    """Point detector implementation using SUMO's E1 detector."""

    def __init__(self, detector_id: str) -> None:
        super().__init__()

        self._id = detector_id

        self._current_time: float = 0  # Current simulation time in seconds
        self._occupied: bool = False  # Start the detector as not occupied
        self._detection_start: float = -1  # Time of the last occupation start

    def tick(self) -> None:
        """Update the detector's internal status."""
        # Update the detectors internal clock
        self._current_time = libsumo.simulation.getTime()

        currently_occupied = (
            libsumo.inductionloop.getLastStepVehicleNumber(self._id) > 0
        )

        # If detector was not occupied previously but now is, detection starts.
        if not self._occupied and currently_occupied:
            self._occupied = True
            self._detection_start = self._current_time

        # If detector was occupied but is no longer, detection ends.
        elif self._occupied and not currently_occupied:
            self._occupied = False
            self._detection_start = -1

    @property
    def is_occupied(self) -> bool:
        """True if detector currently detects a vehicle."""
        return self._occupied

    @property
    def detection_duration(self) -> float:
        """Duration of the current detection in seconds."""
        if not self._occupied:
            return 0

        return self._current_time - self._detection_start
