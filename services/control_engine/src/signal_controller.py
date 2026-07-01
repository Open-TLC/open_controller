from abc import ABC, abstractmethod
from typing import Any


class ControllerStatus:
    def __init__(self, step_count: int, current_phase: str, next_phase: str) -> None:
        self.step_count: int = step_count
        self.current_phase: str = current_phase
        self.next_phase: str = next_phase


class SignalController(ABC):
    """Controller interface for interacting with a signal controller.

    All controllers should use signal groups internally to ensure adequate intergreen
    times between conflicting greens. Signal controller's should be configured with
    a JSON file in a standard format.
    """

    @abstractmethod
    def tick(self) -> None:
        """Advance the controller by one step.
        This updates detections and signal states.
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset controller state.
        All configurations are persisted.
        """
        ...

    @abstractmethod
    def reload(self) -> None:
        """Reload controller from configuration."""
        ...

    @abstractmethod
    def save(self, filename: str) -> None:
        """Save current configuration to a file."""
        ...

    @abstractmethod
    def all_red(self) -> None:
        """Transition to all red.
        Gracefully transition to all red and remain there indefinitely.
        This is a safety feature used for unexpected situations (alien attack?).
        """
        ...

    @property
    @abstractmethod
    def status(self) -> ControllerStatus:
        """Current controller status."""
        ...

    @property
    @abstractmethod
    def status_dict(self) -> dict[str, Any]:
        """Current controller status as a dictionary."""
        ...

    @property
    @abstractmethod
    def signal_states(self) -> str:
        """Signal states in Open Controller format."""
        ...

    @property
    @abstractmethod
    def signal_states_sumo(self) -> str:
        """Signal states in SUMO format."""
        ...
