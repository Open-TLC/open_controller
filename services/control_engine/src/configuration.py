"""Module for reading and parsing Open Controller configuration.

The module is meant to be used by Clockwork.
"""

# Copyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved

import argparse
from typing import Any

import yaml

from .detectors.area_detector import AreaDetector
from .detectors.configuration import DetectorConfiguration
from .detectors.point_detector import PointDetector
from .fixed_time_controller.controller import FixedTimeController
from .signal_controller import SignalController
from .signal_group_controller import PhaseRingController
from .timer import Timer


class ClockworkConf:
    """Configuration object for Clockwork settings."""

    def __init__(
        self,
        filename: str,
        print_status: bool = False,
    ) -> None:
        raw_conf: dict[str, Any]
        with open(filename) as f:
            raw_conf = yaml.safe_load(f)

        self.nats: NatsConf = NatsConf(raw_conf["nats"])
        self.timer: TimerConf = TimerConf(raw_conf["timer"])

        # TODO: Override controllers print_status if print_status is set to True
        self.controllers: list[ControllerConf] = []
        for raw_controller_conf in raw_conf["controllers"]:
            controller_conf = ControllerConf(raw_controller_conf)
            self.controllers.append(controller_conf)

        self.detectors: list[DetectorConfiguration] = []
        for raw_detector_conf in raw_conf["detectors"]:
            detector_conf = DetectorConfiguration(raw_detector_conf)
            self.detectors.append(detector_conf)


class ControllerConf:
    """Configuration object for signal controller settings."""

    def __init__(self, raw_conf: dict[str, Any]) -> None:
        # These must be present in any controller configuration.
        # Method crashes on KeyError on purpose.
        self.type: str = str(raw_conf["type"])
        self.id: str = str(raw_conf["id"])
        self.options: dict[str, Any] = raw_conf["options"]


DEFAULT_NATS_SERVER = "nats://localhost"
DEFAULT_NATS_PORT = 4222
DEFAULT_NATS_MODE = "change"


class NatsConf:
    """Configuration object for Clockwork NATS settings."""

    def __init__(self, raw_conf: dict[str, Any]) -> None:
        self.server = raw_conf.get("server") or DEFAULT_NATS_SERVER
        self.port = raw_conf.get("port") or DEFAULT_NATS_PORT
        mode = raw_conf.get("mode") or DEFAULT_NATS_MODE
        if mode not in ["change", "update"]:
            raise ValueError(
                f"Unknown Clockwork NATS mode {mode}. Supported modes: change, update.",
            )
        self.mode = mode


SUPPORTED_TIMER_MODES: list[str] = ["fixed", "real"]


class TimerConf:
    """Configuration object for timer settings."""

    def __init__(self, raw_conf: dict[str, Any]) -> None:
        timer_mode = str(raw_conf.get("timer_mode"))
        if not timer_mode or timer_mode not in SUPPORTED_TIMER_MODES:
            raise ValueError(
                f"Unknown timer mode {timer_mode}. "
                f"Currently supported modes {SUPPORTED_TIMER_MODES}.",
            )
        self.mode: str = timer_mode

        # The length of a simulation step (s).
        self.simulation_step: float = float(raw_conf["simulation_step"])
        # The time between controller updates (s).
        self.controller_step: float = float(raw_conf["controller_step"])
        # When running in
        self.real_time_multiplier: float = float(raw_conf["real_time_multiplier"])

    @property
    def timer_prm(self) -> dict[str, Any]:
        """Get settings in legacy timer parameter format."""
        return {
            "timer_mode": self.mode,
            "time_step": self.simulation_step,
            "real_time_multiplier": self.real_time_multiplier,
        }


def read_command_line():
    """Read command line arguments."""
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--conf-file",
        help="Open Controller configuration file (filename).",
        required=True,
    )

    parser.add_argument(
        "--print-status",
        help="Print controller status on every update (true/false) (default: false).",
        action="store_true",
        required=False,
    )

    return parser.parse_args()


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
