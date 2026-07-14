from abc import ABC, abstractmethod
from typing import Any

from .configuration import ControllerConf
from .detectors.area_detector import AreaDetector
from .detectors.point_detector import PointDetector
from .signal_group_controller import PhaseRingController
from .timer import Timer


class ControllerStatus:
    """Status of a controller."""

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

    @property
    @abstractmethod
    def id(self) -> str:
        """Controllers ID."""
        ...

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


SUPPORTED_CONTROLLER_TYPES: list[str] = ["phasering", "syvari", "bumblebee"]


def create_controller(
    conf: ControllerConf,
    timer: Timer,
    detectors: tuple[list[PointDetector], list[AreaDetector]],
) -> SignalController:
    """Create controller based on provided configuration.

    Args:
        conf: Controller configuration used to create the controller.
        timer: Timer used by the controller.
        detectors: All available detectors. The controller will only get the ones it
            needs based on the configuration. This is necessary as the way detectors
            are configured can vary between controllers.

    Returns:
        The created signal controller.

    Raises:
        ValueErrors: Unknown controller type.
        ValueError: Detector configured in controller can't be found in 'detectors'.

    """
    controller_type = conf.type

    controller: SignalController
    if controller_type == "phasering":
        # TODO: Migrate PhaseRingController to standard signal controller.
        controller = PhaseRingController(conf.options, timer)
    elif controller_type == "syvari":
        raise NotImplementedError("SYVARI controller creation is not yet supported.")
    elif controller_type == "bumblebee":
        raise NotImplementedError("Bumblebee controller creation is not yet supported.")
    else:
        raise ValueError(
            f"Controller type {controller_type} is not supported. "
            f"Currently supported controller types: {SUPPORTED_CONTROLLER_TYPES}.",
        )

    return controller
