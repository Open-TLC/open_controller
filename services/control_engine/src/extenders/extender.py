"""Abstract extender class implementation."""

from abc import ABC, abstractmethod


class Extender(ABC):
    """Active green extender interface."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Get ID of the extender."""

    @property
    @abstractmethod
    def is_extending(self) -> bool:
        """Check if extender is extending."""
        ...

    @abstractmethod
    def tick(self) -> None:
        """Update extending status."""
        ...
