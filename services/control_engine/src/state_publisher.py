import json
import time
from datetime import UTC, datetime

from nats.aio.client import Client

GROUP_CONTROL_SUBJECT_PREFIX = "group.control"


class StatePublisher:
    """Handles publishing controller states."""

    def __init__(
        self,
        nc: Client,
        controller_id: str,
        group_ids: list[str],
        mode: str,
    ) -> None:
        """Create state publisher.

        Args:
            nc: NATS client used to publish messages.
            controller_id: ID of the signal controller.
            group_ids: List of signal group IDs in the same order as the states.
            mode: "update", "change", or "group_change"

        """
        self._controller_id = controller_id
        self._nc: Client = nc

        controller_control_subject = f"{GROUP_CONTROL_SUBJECT_PREFIX}.{controller_id}"
        self._controller_subject = controller_control_subject

        self._group_ids = group_ids.copy()

        self._mode = mode
        self._update_always: bool = mode == "update"

        self._old_states: str | dict[str, str] | None = None
        self._old_group_states: dict[str, str] | None = None

    async def publish_initial_red(self) -> None:
        """Send the startup red command to every group in group_change mode."""
        if self._mode != "group_change":
            return

        red_states = {group_id: "a" for group_id in self._group_ids}
        await self._publish_to_nats(red_states)
        self._old_group_states = red_states

    async def publish(self, states: str | dict[str, str]) -> None:
        """Publish states to controller state subject."""
        if isinstance(states, dict):
            if set(states) != set(self._group_ids):
                raise ValueError(
                    "Logical signal group IDs don't match the publisher mapping: "
                    f"{sorted(states)} != {sorted(self._group_ids)}.",
                )
        elif len(states) != len(self._group_ids):
            raise ValueError(
                "Number of states doesn't correspond to the number of signal groups, "
                f"{len(states)} != {len(self._group_ids)}.",
            )

        return await self._publish_if_necessary(states)

    async def _publish_if_necessary(self, states: str | dict[str, str]) -> None:
        if self._mode == "group_change":
            current_states = self._states_by_group(states)
            if self._old_group_states is None:
                # Also support direct use of StatePublisher without Clockwork's
                # startup hook: send the red baseline before any live states.
                await self.publish_initial_red()

            assert self._old_group_states is not None
            changed_states = {
                group_id: state
                for group_id, state in current_states.items()
                if self._old_group_states[group_id] != state
            }
            if changed_states:
                await self._publish_to_nats(
                    changed_states,
                    group_ids=list(changed_states),
                )
            self._old_group_states = current_states
            return

        changed: bool = states != self._old_states
        self._old_states = states

        # States are published if they have changed or if Clockwork is set to always
        # publish states.
        if changed or self._update_always:
            await self._publish_to_nats(states)

    def _states_by_group(self, states: str | dict[str, str]) -> dict[str, str]:
        if isinstance(states, dict):
            return states.copy()
        return {
            group_id: states[index]
            for index, group_id in enumerate(self._group_ids)
        }

    async def _publish_to_nats(
        self,
        states: str | dict[str, str],
        group_ids: list[str] | None = None,
    ) -> None:
        selected_group_ids = self._group_ids if group_ids is None else group_ids
        if isinstance(states, dict):
            state_items = [
                (group_id, int(group_id), states[group_id])
                for group_id in selected_group_ids
            ]
        else:
            state_items = [
                (group_id, i, states[i])
                for i, group_id in enumerate(selected_group_ids)
            ]

        for group_id, group_number, state in state_items:
            subject = f"{self._controller_subject}.{group_id}"

            msg = (
                _GroupStateMessage(subject, state, group_number, _is_green(state))
                .to_json()
                .encode()
            )

            await self._nc.publish(subject, msg)


GREEN_SUBSTATES = ["1", "4", "5"]


def _is_green(state: str) -> bool:
    return state in GREEN_SUBSTATES


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
