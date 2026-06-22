from abc import ABC, abstractmethod


class AreaDetector(ABC):
    """Detector interface for interacting with an area detector.

    This kind of detector works similar to a radar / camera in
    a sense that it can monitor an area instead of just a single
    point like induction loop.
    """

    @abstractmethod
    def vehicle_count(self) -> float:
        """Return the total number or vehicles currently in the area."""
        ...

    @abstractmethod
    def average_speed(self) -> float:
        """Return the average speed (m/s) of a vehicle currently in the area."""
        ...

    @abstractmethod
    def average_time_loss(self) -> float:
        """Return the average time loss (s) experienced by vehicles in the area."""
        ...
