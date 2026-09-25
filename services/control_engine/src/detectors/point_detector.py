from abc import ABC, abstractmethod

TRANSIT_VEHICLE_TYPES: list[str] = ["bus", "tram"]


class PointDetector(ABC):
    """Detector interface for interacting with a point detector.

    This kind of detector works similar to an induction loop in
    a sense that it can monitor a single point and report, whether
    vehicles exist above it.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """ID of the detector."""
        ...

    @abstractmethod
    def tick(self) -> None:
        """Update the detector."""
        ...

    @property
    @abstractmethod
    def is_occupied(self) -> bool:
        """True if detector currently has a vehicle detected."""
        ...

    @property
    @abstractmethod
    def detection_duration(self) -> float:
        """Duration of the current detection in seconds."""
        ...


class TransitPointDetector(PointDetector):
    """Point detector for detecting transit vehicles."""
