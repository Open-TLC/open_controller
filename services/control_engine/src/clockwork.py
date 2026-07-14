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
import time

from nats import connect
from nats.aio.client import Client

from .configuration import ClockworkConf, TimerConf, read_command_line
from .signal_controller import SignalController, create_controller
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

        self._timer: ControllerTimer = ControllerTimer(self._conf.timer)

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

            # Create state publisher for the controller.
            instance._publishers[controller.id] = StatePublisher(nc, controller.id)

        return instance

    async def run(self) -> None:
        """Start controller runner."""
        if len(self._controllers) == 0:
            raise ValueError(
                "No controllers configured for the Clockwork instance. "
                "Please configure controllers in --conf-file.",
            )

        while True:
            # Block until it's time to update controller and publish new states.
            self._timer.wait_for_update()

            # Update all controllers and publish their states.
            for controller in self._controllers:
                controller.tick()
                new_states: str = controller.signal_states
                await self._publishers[controller.id].publish(new_states)


STATUS_SUBJECT_PREFIX = "clockwork.status"


class ControllerTimer(Timer):
    """Timer for controller operations.

    Provides convenience method to block until next controller
    update. This is meant to be used only by Clockwork.
    """

    def __init__(self, conf: TimerConf):
        """Create controller timer.

        Args:
            conf: Configuration for timer.

        """
        super().__init__(conf.timer_prm)
        self._step_length = conf.controller_step
        self._last_updated = self.seconds
        self._real: bool = conf.mode == "real"

    def wait_for_update(self) -> None:
        """Wait for next update time.

        This sleeps until it is again time to update the controller.
        """
        next_update: float = self._last_updated + self._step_length
        while next_update > self.seconds:
            # If timer mode is real, this needs to block until next
            # timer update.
            next_update_real = next_update * self._time_multiplier
            while self._real and next_update_real > self.real_seconds:
                time.sleep(0.1)
                self.sleep_tick()

            # Tick timer until next update passes.
            self.tick()

        self._last_updated = self.seconds


class StatePublisher:
    """Handles publishing controller states."""

    def __init__(self, nc: Client, controller_id: str) -> None:
        """Create state publisher.

        Args:
            nc: NATS client used to publish messages.
            controller_id: ID of the signal controller.

        """
        self._controller_id = controller_id
        self._nc: Client = nc

        state_subject = f"{STATUS_SUBJECT_PREFIX}.{controller_id}"
        self._subject = state_subject

    async def publish(self, states: str) -> None:
        """Publish states to controller state subject."""
        await self._nc.publish(self._subject, states.encode())


if __name__ == "__main__":
    asyncio.run(main())
