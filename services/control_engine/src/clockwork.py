"""Open Controller signal control service.

This module runs a signal controller and sends the provided signal states to NATS.
"""

# Open Controller, an open source traffic signal control platform
# URL: https://www.opencontroller.org
# Copyright 2023 - 2024 by Conveqs Oy, Kari Koskinen and others
# This program has been released under EUPL-1.2 license which is available at
# URL: https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12

import argparse
import asyncio

from nats import connect
from nats.aio.client import Client
from nats.aio.msg import Msg

from .configuration import (
    ClockworkConf,
    read_command_line,
)
from .controller_creation import create_controller
from .detectors.configuration import create_detectors
from .signal_controller import SignalController
from .state_publisher import StatePublisher
from .timer import Timer


async def main() -> None:
    """Run control engine."""
    args = read_command_line()

    clockwork = await Clockwork.create(args)
    await clockwork.run()


COMMAND_SUBJECT = "clockwork.command"
STATUS_SUBJECT = "clockwork.status"


class Clockwork:
    """Open Controller signal controller runner."""

    def __init__(self, args: argparse.Namespace) -> None:
        print_status: bool = args.print_status

        self._conf_file: str = args.conf_file
        self._conf = ClockworkConf(self._conf_file, print_status)

        self._nc: Client

        self._publishers: dict[str, StatePublisher] = {}
        self._controllers: list[SignalController] = []

        self._timer: Timer = Timer(self._conf.timer)

        # Clockwork caches the current signal states for each controller.
        # This is used to publish new states only when the state changes.
        self._signal_states: dict[str, str] = {}

        self._keep_alive: bool = True
        self._update: bool = False

        self._state_changed: asyncio.Event = asyncio.Event()

    @classmethod
    async def create(cls, args: argparse.Namespace) -> "Clockwork":
        """Asynchronous constructor for Clockwork."""
        instance = cls(args)

        nats_url: str = instance._conf.nats.server
        nats_port: int = instance._conf.nats.port
        nats_address: str = f"nats://{nats_url}:{nats_port}"
        nc: Client = await connect(nats_address)
        instance._nc = nc

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

        self._timer.reset()

        # Start response services for status requests and commands.
        status_sub = await self._nc.subscribe(
            STATUS_SUBJECT,
            cb=self._handle_status,
        )
        command_sub = await self._nc.subscribe(COMMAND_SUBJECT, cb=self._handle_command)

        await self._nc.publish(STATUS_SUBJECT, b"started")

        try:
            while self._keep_alive:
                # When not updating, wait for state to change (start or exit) before
                # advancing.
                if not self._update:
                    await self._state_changed.wait()
                    self._state_changed.clear()
                    continue

                # Synchronize update cycle to the timer.
                await asyncio.sleep(self._timer.wall_time_to_next_step())

                # Check flags again in case they changed during sleep.
                if not self._update or not self._keep_alive:
                    continue

                # Advancing timer.
                self._timer.tick()

                # Update all controllers and publish their states.
                for controller in self._controllers:
                    controller.tick()
                    new_states: str = controller.signal_states
                    await self._publishers[controller.id].publish(new_states)
                    self._signal_states[controller.id] = new_states

        finally:
            # Clean up command subscription and NATS client.
            await command_sub.unsubscribe()
            await status_sub.unsubscribe()
            await self._nc.drain()

    async def _handle_command(self, msg: Msg) -> None:
        command = msg.data.decode().strip()

        if command == "stop":
            print("Stopping the controller")
            self._update = False
            self._state_changed.set()

        elif command == "start":
            print("Starting the controller")
            self._timer.reset()
            for controller in self._controllers:
                controller.reset()
            self._update = True
            self._state_changed.set()

        elif command == "exit":
            print("Exiting Clockwork")
            self._keep_alive = False
            self._update = False
            self._state_changed.set()

    async def _handle_status(self, msg: Msg) -> None:
        status = "updating" if self._update else "idling"
        if msg.reply:
            await msg.respond(status.encode())


if __name__ == "__main__":
    asyncio.run(main())
