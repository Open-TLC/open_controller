import json
from typing import Any

from nats.aio.client import Client
from nats.aio.msg import Msg

from .area_detector import AreaDetector


class TrafficIndicatorsAreaDetector(AreaDetector):
    """AreaDetector implementation using data from Traffic Indicators."""

    def __init__(
        self,
        junction_id: str,
        group_id: str,
    ) -> None:
        super().__init__()
        self._junction_id = junction_id
        self._group_id = group_id

        self._nc: Client | None = None

        self._vehicle_count: float = 0.0
        self._average_speed: float = 0.0
        self._average_time_loss: float = 0.0

    @classmethod
    async def create(
        cls,
        nc: Client,
        junction_id: str,
        group_id: str,
    ) -> "TrafficIndicatorsAreaDetector":
        """Instantiate detector needing asynchronous setup."""
        instance = cls(junction_id, group_id)
        instance._nc = nc

        detection_subject = f"group.e3.{junction_id}.{group_id}"

        # Subscriptions stay the same
        await instance._nc.subscribe(
            detection_subject,
            cb=instance._update_vehicle_count,
        )
        await instance._nc.subscribe(
            detection_subject,
            cb=instance._update_average_speed,
        )
        await instance._nc.subscribe(
            detection_subject,
            cb=instance._update_average_time_loss,
        )

        return instance

    def tick(self) -> None:
        """Override tick method to implement interface.

        Traffic Indicators detectors don't need to be manually ticked
        as they update asynchronously when receiving detections from
        NATS.
        """
        pass

    @property
    def vehicle_count(self) -> float:
        """Total number of vehicles currently in detection area."""
        return self._vehicle_count

    @property
    def average_speed(self) -> float:
        """Average speed (m/s) of vehicles in the detection area."""
        return self._average_speed

    @property
    def average_time_loss(self) -> float:
        """Average time loss (s) of vehicles in the detection area."""
        raise NotImplementedError("Traffic Indicators doesn't provide time losses.")
        return self._average_time_loss

    async def _update_vehicle_count(self, msg: Msg) -> None:
        data = json.loads(msg.data.decode())

        vehicle_count: int | None = data.get("count")

        # If no vehicles are detected, vehicle count is zeroed.
        if not vehicle_count:
            self._vehicle_count = 0
            return

        self._vehicle_count = float(vehicle_count)

    async def _update_average_speed(self, msg: Msg) -> None:
        data = json.loads(msg.data.decode())

        # Vehicles by ID
        vehicles: dict[str, dict[str, Any]] | None = data.get("objects")

        vehicle_count: int | None = data.get("count")

        # If no vehicles are detected, average speed is zeroed.
        if not vehicles or not vehicle_count:
            self._average_speed = 0
            return

        speed_sum: float = sum(veh["speed"] for veh in vehicles.values())

        self._average_speed = speed_sum / vehicle_count

    async def _update_average_time_loss(self, msg: Msg) -> None:
        pass
