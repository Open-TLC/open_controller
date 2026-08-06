"""Module for reading and parsing Open Controller configuration.

The module is meant to be used by Clockwork.
"""

# Copyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved

import argparse
from typing import Any

import yaml

from .detectors.configuration import DetectorConfiguration


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
        self.publisher: PublisherConf = PublisherConf(
            raw_conf["clockwork"]["publisher"],
        )

        # TODO: Override controllers print_status if print_status is set to True
        self.controllers: list[ControllerConf] = []
        for raw_controller_conf in raw_conf["clockwork"]["controllers"]:
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


class NatsConf:
    """Configuration object for Clockwork NATS settings."""

    def __init__(self, raw_conf: dict[str, Any]) -> None:
        self.server = raw_conf.get("server") or DEFAULT_NATS_SERVER
        self.port = raw_conf.get("port") or DEFAULT_NATS_PORT


DEFAULT_PUBLISHER_MODE = "change"


class PublisherConf:
    """Configuration object for Clockwork state publisher."""

    def __init__(self, raw_conf: dict[str, Any]) -> None:
        mode = raw_conf.get("mode") or DEFAULT_PUBLISHER_MODE
        if mode not in ["change", "update"]:
            raise ValueError(
                f"Unknown publisher mode {mode}. Supported modes: change, update.",
            )
        self.mode = mode


SUPPORTED_TIMER_MODES: list[str] = ["fixed", "real"]


class TimerConf:
    """Configuration object for timer settings."""

    def __init__(self, raw_conf: dict[str, Any]) -> None:
        timer_mode = str(raw_conf.get("timer_mode"))
        if timer_mode not in SUPPORTED_TIMER_MODES:
            raise ValueError(
                f"Unknown timer mode {timer_mode}. "
                f"Currently supported modes {SUPPORTED_TIMER_MODES}.",
            )
        self.mode: str = timer_mode

        # The length of a simulation step (s).
        self.time_step: float = float(raw_conf["time_step"])

        # When running in real mode, we might want to change the speed of time.
        self.real_time_multiplier: float = float(raw_conf["real_time_multiplier"])


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
