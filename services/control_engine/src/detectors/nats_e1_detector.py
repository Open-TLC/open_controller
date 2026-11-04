"""E1 point detector updated from SimEngine detector messages over NATS."""

import json
import time

from nats.aio.client import Client
from nats.aio.msg import Msg

from .point_detector import PointDetector


class NatsE1PointDetector(PointDetector):
    """Point detector whose occupancy is received from a remote SimEngine."""

    def __init__(self, detector_id: str) -> None:
        self._id = detector_id
        self._occupied = False
        self._detection_start: float | None = None

    @classmethod
    async def create(
        cls,
        nc: Client,
        detector_id: str,
        topic_prefix: str = "detector.control",
    ) -> "NatsE1PointDetector":
        """Create the detector and subscribe to its occupancy subject."""
        instance = cls(detector_id)
        await nc.subscribe(
            f"{topic_prefix}.{detector_id}",
            cb=instance._update_from_message,
        )
        return instance

    @property
    def id(self) -> str:
        return self._id

    def tick(self) -> None:
        """NATS updates the detector asynchronously, so no polling is needed."""

    @property
    def is_occupied(self) -> bool:
        return self._occupied

    @property
    def detection_duration(self) -> float:
        if self._detection_start is None:
            return 0.0
        return time.monotonic() - self._detection_start

    async def _update_from_message(self, msg: Msg) -> None:
        data = json.loads(msg.data.decode())
        occupied = data.get("loop_on")
        if not isinstance(occupied, bool):
            return

        if occupied and not self._occupied:
            self._detection_start = time.monotonic()
        elif not occupied:
            self._detection_start = None

        self._occupied = occupied
