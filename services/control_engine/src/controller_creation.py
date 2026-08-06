from services.control_engine.src.detectors.area_detector import AreaDetector
from services.control_engine.src.detectors.point_detector import PointDetector
from services.control_engine.src.fixed_time_controller.controller import (
    FixedTimeController,
)
from services.control_engine.src.signal_group_controller import PhaseRingController

from .configuration import ControllerConf
from .signal_controller import SignalController
from .timer import Timer

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
    elif controller_type == "fixed_time":
        controller = FixedTimeController(conf.id, timer, conf.options)
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
