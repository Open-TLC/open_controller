from nats import connect
from nats.aio.msg import Msg

from .area_detector import AreaDetector


class TrafficIndicatorsDetectionArea:
    """Traffic Indicators area specifier."""

    def __init__(
        self,
        country: str,
        municipality: str,
        junction_id: str,
        detector_id: str,
    ) -> None:
        self.country = country
        self.municipality = municipality
        self.junction_id = junction_id
        self.detector_id = detector_id


class TrafficIndicatorsAreaDetector(AreaDetector):
    """AreaDetector implementation using data from Traffic Indicators."""

    def __init__(
        self,
        area: TrafficIndicatorsDetectionArea,
    ) -> None:
        super().__init__()
        self._area = area
        self._nc = None

        self._vehicle_count: float = 0.0
        self._average_speed: float = 0.0
        self._average_time_loss: float = 0.0

    @classmethod
    async def create(
        cls,
        nats_url: str,
        nats_port: int,
        area: TrafficIndicatorsDetectionArea,
    ) -> "TrafficIndicatorsAreaDetector":
        """Instantiate detector needing asynchronous setup."""
        # Create instance of detector class.
        instance = cls(area)

        # Create NATS client.
        instance._nc = await connect(f"nats://{nats_url}:{nats_port}")

        # Build subjects for queue lengths, average speeds, and average time losses.
        queue_subject = (
            f"indicators.queue_length"
            f".{area.country}.{area.municipality}"
            f".{area.junction_id}.{area.detector_id}"
        )
        speed_subject = (
            f"indicators.avg_speed"
            f".{area.country}.{area.municipality}"
            f".{area.junction_id}.{area.detector_id}"
        )
        loss_subject = (
            f"indicators.avg_time_loss"
            f".{area.country}.{area.municipality}"
            f".{area.junction_id}.{area.detector_id}"
        )

        # Callback functions update instance variables for
        # queues, speeds, and time losses asynchronously.
        await instance._nc.subscribe(queue_subject, cb=instance._update_vehicle_count)
        await instance._nc.subscribe(speed_subject, cb=instance._update_average_speed)
        await instance._nc.subscribe(
            loss_subject,
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
        return self._average_time_loss

    async def _update_vehicle_count(self, msg: Msg) -> None:
        data = msg.data.decode()

        # TODO: Figure out the data format and update
        # instance variable _vehicle_count based on it.

        print(data)

    async def _update_average_speed(self, msg: Msg) -> None:
        data = msg.data.decode()

        # TODO: Figure out the data format and update
        # instance variable _average_speed based on it.

        print(data)

    async def _update_average_time_loss(self, msg: Msg) -> None:
        data = msg.data.decode()

        # TODO: Figure out the data format and update
        # instance variable _average_time_loss based on it.

        print(data)
