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
import json
import time
from datetime import UTC, datetime

from nats import connect
from nats.aio.client import Client

from .configuration import (
    ClockworkConf,
    TimerConf,
    create_controller,
    read_command_line,
)
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

        self._timer: ControllerTimer = ControllerTimer(self._conf.timer)

        # Clockwork caches the current signal states for each controller.
        # This is used to publish new states only when the state changes.
        self._signal_states: dict[str, str] = {}

        # If mode is set to update, clockwork will publish states regardless of whether
        # they have changed. Other wise they will only be published once changed.
        self._update_always: bool = self._conf.nats.mode == "update"

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
            # Block until it's time to update controller and publish new states.
            self._timer.wait_for_update()

            # Update all controllers and publish their states.
            for controller in self._controllers:
                controller.tick()
                new_states: str = controller.signal_states
                await self._publish_if_necessary(new_states, controller.id)

                # New states are saved.
                self._signal_states[controller.id] = new_states

    async def _publish_if_necessary(self, new_states: str, controller_id: str) -> None:
        changed: bool = new_states != self._signal_states[controller_id]
        self._signal_states[controller_id] = new_states
        # States are published if they have changed or if Clockwork is set to always
        # publish states.
        if changed or self._update_always:
            await self._publishers[controller_id].publish(new_states)


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


class _GroupStateMessage:
    def __init__(
        self,
        control_subject: str,
        substate: str,
        group_number: int,
        is_green: bool,
    ) -> None:
        self.control_subject = control_subject
        self.substate = substate
        self.group_num = group_number
        self.is_green = is_green

    def _get_nanosecond_timestamp(self) -> str:
        """Generate UTC ISO 8601 timestamp with nanosecond precision."""
        ns = time.time_ns()
        seconds = ns // 1_000_000_000
        nanos = ns % 1_000_000_000
        dt = datetime.fromtimestamp(seconds, tz=UTC)
        return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{nanos:09d}"

    def to_dict(self) -> dict:
        """Convert message to dictionary representation."""
        return {
            "id": self.control_subject,
            "tstamp": self._get_nanosecond_timestamp(),
            "substate": self.substate,
            "group": self.group_num,
            "green": self.is_green,
        }

    def to_json(self, indent: int | None = None) -> str:
        """Serialize the message object into a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


GROUP_CONTROL_SUBJECT_PREFIX = "group.control"


class StatePublisher:
    """Handles publishing controller states."""

    def __init__(self, nc: Client, controller_id: str, group_ids: list[str]) -> None:
        """Create state publisher.

        Args:
            nc: NATS client used to publish messages.
            controller_id: ID of the signal controller.
            group_ids: List of signal group IDs in the same order as the states.

        """
        self._controller_id = controller_id
        self._nc: Client = nc

        controller_control_subject = f"{GROUP_CONTROL_SUBJECT_PREFIX}.{controller_id}"
        self._controller_subject = controller_control_subject

        self._group_ids = group_ids.copy()

    async def publish(self, states: str) -> None:
        """Publish states to controller state subject."""
        if len(states) != len(self._group_ids):
            raise ValueError(
                "Number of states doesn't correspond to the number of signal groups, "
                f"{len(states)} != {len(self._group_ids)}.",
            )

        for i, group_id in enumerate(self._group_ids):
            subject = f"{self._controller_subject}.{group_id}"

            state = states[i]

            msg = (
                _GroupStateMessage(subject, state, i, _is_green(state))
                .to_json()
                .encode()
            )

            await self._nc.publish(subject, msg)


GREEN_SUBSTATES = ["1", "4", "5"]


def _is_green(state: str) -> bool:
    return state in GREEN_SUBSTATES


if __name__ == "__main__":
    asyncio.run(main())
