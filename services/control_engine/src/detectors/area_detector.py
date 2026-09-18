from abc import ABC, abstractmethod


class AreaDetector(ABC):
    """Detector interface for interacting with an area detector.

    This kind of detector works similar to a radar / camera in
    a sense that it can monitor an area instead of just a single
    point like induction loop.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """ID of the detector."""
        ...

    @abstractmethod
    def tick(self) -> None:
        """Update the detectors internal state."""
        ...

    @property
    @abstractmethod
    def vehicle_count(self) -> float:
        """Total number or vehicles currently in the area."""
        ...

    @property
    @abstractmethod
    def average_speed(self) -> float:
        """Average speed (m/s) of a vehicle currently in the area."""
        ...

    @property
    @abstractmethod
    def average_time_loss(self) -> float:
        """Average time loss (s) experienced by vehicles in the area."""
        ...


class TransitAreaDetector(AreaDetector):
    """Area detector for detecting transit vehicles."""
