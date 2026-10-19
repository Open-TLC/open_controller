from abc import ABC, abstractmethod


class Requester(ABC):
    """Green requester object."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Get ID of the requester."""
        ...

    @abstractmethod
    def tick(self) -> None:
        """Update the requesting status."""
        ...

    @property
    @abstractmethod
    def is_requesting(self) -> bool:
        """Check if green request is active."""
        ...
