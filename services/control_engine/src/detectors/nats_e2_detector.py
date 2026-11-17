"""E2 area detector updated from SimEngine detector messages over NATS."""

import json

from nats.aio.client import Client
from nats.aio.msg import Msg

from .area_detector import AreaDetector


class NatsE2AreaDetector(AreaDetector):
    """Area detector whose measurements arrive from a remote SimEngine."""

    def __init__(self, detector_id: str) -> None:
        self._id = detector_id
        self._vehicle_count = 0.0
        self._average_speed = 0.0
        self._average_time_loss = 0.0

    @classmethod
    async def create(
        cls,
        nc: Client,
        detector_id: str,
        topic_prefix: str = "detector.control",
    ) -> "NatsE2AreaDetector":
        """Create the detector and subscribe to its measurements subject."""
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
    def vehicle_count(self) -> float:
        return self._vehicle_count

    @property
    def average_speed(self) -> float:
        return self._average_speed

    @property
    def average_time_loss(self) -> float:
        return self._average_time_loss

    async def _update_from_message(self, msg: Msg) -> None:
        data = json.loads(msg.data.decode())
        try:
            vehicle_count = max(0.0, float(data["vehicle_count"]))
            average_speed = max(0.0, float(data["average_speed"]))
            average_time_loss = max(0.0, float(data["average_time_loss"]))
        except (KeyError, TypeError, ValueError):
            return

        self._vehicle_count = vehicle_count
        self._average_speed = average_speed
        self._average_time_loss = average_time_loss
