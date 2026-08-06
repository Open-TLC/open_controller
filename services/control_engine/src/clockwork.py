"""Open Controller signal control service.

This module runs a signal controller and sends the provided signal states to NATS.
"""
#
# Open Controller, an open source traffic signal control platform
# URL: https://www.opencontroller.org
# Copyright 2023 - 2024 by Conveqs Oy, Kari Koskinen and others
# This program has been released under EUPL-1.2 license which is available at
# URL: https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12
#

import argparse
import asyncio

from nats import connect
from nats.aio.client import Client

from services.control_engine.src.state_publisher import StatePublisher

from .configuration import (
    ClockworkConf,
    read_command_line,
)
from .controller_creation import create_controller
from .detectors.configuration import create_detectors
from .signal_controller import SignalController
from .timer import Timer


async def main() -> None:
    """Run control engine."""
    args = read_command_line()

    clockwork = await Clockwork.create(args)
    await clockwork.run()


# TODO: Start accepting commands
COMMAND_SUBJECT_PREFIX = "clockwork.command"


class Clockwork:
    """Open Controller signal controller runner."""

    def __init__(self, args: argparse.Namespace) -> None:
        print_status: bool = args.print_status

        self._conf_file: str = args.conf_file
        self._conf = ClockworkConf(self._conf_file, print_status)

        self._publishers: dict[str, StatePublisher] = {}
        self._controllers: list[SignalController] = []

        self._timer: Timer = Timer(self._conf.timer)

        # Clockwork caches the current signal states for each controller.
        # This is used to publish new states only when the state changes.
        self._signal_states: dict[str, str] = {}

    @classmethod
    async def create(cls, args: argparse.Namespace) -> "Clockwork":
        """Asynchronous constructor for Clockwork."""
        instance = cls(args)

        nats_url: str = instance._conf.nats.server
        nats_port: int = instance._conf.nats.port
        nats_address: str = f"nats://{nats_url}:{nats_port}"
        nc: Client = await connect(nats_address)

        detectors = await create_detectors(instance._conf.detectors, nc=nc)

        for conf in instance._conf.controllers:
            # Create controller.
            controller = create_controller(conf, instance._timer, detectors)
            instance._controllers.append(controller)

            example_states = controller.signal_states
            group_nums = [str(i) for i, _ in enumerate(example_states)]

            # Create state publisher for the controller.
            instance._publishers[controller.id] = StatePublisher(
                nc,
                controller.id,
                group_nums,
                instance._conf.publisher.mode,
            )

        return instance

    async def run(self) -> None:
        """Start controller runner."""
        if len(self._controllers) == 0:
            raise ValueError(
                "No controllers configured for the Clockwork instance. "
                "Please configure controllers in --conf-file.",
            )

        for controller in self._controllers:
            self._signal_states[controller.id] = controller.signal_states

        while True:
            # Advancing timer.
            self._timer.tick()

            # Update all controllers and publish their states.
            for controller in self._controllers:
                controller.tick()
                new_states: str = controller.signal_states
                await self._publishers[controller.id].publish(new_states)

                # New states are saved.
                self._signal_states[controller.id] = new_states


if __name__ == "__main__":
    asyncio.run(main())
