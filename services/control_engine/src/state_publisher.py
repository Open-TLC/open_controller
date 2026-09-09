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
            mode: "update" or "change"

        """
        self._controller_id = controller_id
        self._nc: Client = nc

        controller_control_subject = f"{GROUP_CONTROL_SUBJECT_PREFIX}.{controller_id}"
        self._controller_subject = controller_control_subject

        self._group_ids = group_ids.copy()

        self._update_always: bool = mode == "update"

        self._old_states: str = ""  # Previous states for keeping track of changes

    async def publish(self, states: str) -> None:
        """Publish states to controller state subject."""
        if len(states) != len(self._group_ids):
            raise ValueError(
                "Number of states doesn't correspond to the number of signal groups, "
                f"{len(states)} != {len(self._group_ids)}.",
            )

        return await self._publish_if_necessary(states)

    async def _publish_if_necessary(self, states: str) -> None:
        changed: bool = states != self._old_states
        self._old_states = states

        # States are published if they have changed or if Clockwork is set to always
        # publish states.
        if changed or self._update_always:
            await self._publish_to_nats(states)

    async def _publish_to_nats(self, states: str) -> None:
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
