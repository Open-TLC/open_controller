from nats.aio.client import Client

from services.control_engine.src.detectors.traffic_indicators_area_detector import (
    TrafficIndicatorsAreaDetector,
)
from services.control_engine.src.detectors.nats_e1_detector import (
    NatsE1PointDetector,
)
from services.control_engine.src.detectors.nats_e2_detector import (
    NatsE2AreaDetector,
)

from .area_detector import AreaDetector
from .point_detector import PointDetector
from .sumo_e1_detector import E1PointDetector
from .sumo_e2_detector import E2AreaDetector
from .sumo_e3_detector import E3AreaDetector

SUPPORTED_DETECTOR_TYPES = [
    "e1_detector",
    "e2_detector",
    "e3_detector",
    "traffic_indicators_detector",
]


class DetectorConfiguration:
    """Configuration object used to confire abstract detectors.

    Args:
        conf: Dictionary of detector id and type.

    Raises:
        ValueError: If detector type is not in te list of supported types.

    """

    def __init__(self, conf: dict[str, str]) -> None:
        det_type = conf["type"]
        if det_type not in SUPPORTED_DETECTOR_TYPES:
            raise ValueError(f"Detector of type {det_type} is not supported")

        self.type = det_type
        self.id = conf["id"]
        self.options = conf.get("options", {})


async def create_detectors(
    detector_configurations: list[DetectorConfiguration],
    nc: Client | None = None,
) -> tuple[list[PointDetector], list[AreaDetector]]:
    """Create detectors from configurations.

    Make sure to provide NATS client when creating Traffic Indicators detectors.

    Args:
        detector_configurations: List of detector configuration objects.
        nc: Optional NATS client.

    Returns:
        Tuple containing created point detectors and area detectors.

    """
    point_detectors: list[PointDetector] = []
    area_detectors: list[AreaDetector] = []

    for conf in detector_configurations:
        if conf.type == SUPPORTED_DETECTOR_TYPES[0]:
            if nc is None:
                # Integrated SimEngine and Clockwork share one libsumo instance.
                point_detectors.append(E1PointDetector(conf.id))
            else:
                # In distributed mode, SUMO runs in SimEngine's process and its
                # detector state arrives through NATS.
                topic_prefix = conf.options.get(
                    "topic_prefix",
                    "detector.control",
                )
                point_detectors.append(
                    await NatsE1PointDetector.create(nc, conf.id, topic_prefix),
                )

        elif conf.type == SUPPORTED_DETECTOR_TYPES[1]:
            if nc is None:
                area_detectors.append(E2AreaDetector(conf.id))
            else:
                topic_prefix = conf.options.get(
                    "topic_prefix",
                    "detector.control",
                )
                area_detectors.append(
                    await NatsE2AreaDetector.create(nc, conf.id, topic_prefix),
                )

        elif conf.type == SUPPORTED_DETECTOR_TYPES[2]:
            area_detectors.append(E3AreaDetector(conf.id))

        elif conf.type == SUPPORTED_DETECTOR_TYPES[3]:
            if nc is None:
                raise ValueError(
                    "Found Traffic Indicators detector in "
                    "configuration, yet no NATS client was "
                    "provided. You must provide a NATS client "
                    "when creating Traffic Indicators detectors",
                )
            # FIXME: This is a bit hacky, but for now Traffic Indicators indexes
            # area detections based on junction and signal group. Thus we need
            # to index the controllers in the same matter. In the future we should
            # start indexing Traffic Indicators areas by arbitrary identifiers, as
            # they aren't strictly binded to junctions or groups.
            (junction_id, group_id) = conf.id.split(".", maxsplit=1)
            area_detectors.append(
                await TrafficIndicatorsAreaDetector.create(nc, junction_id, group_id),
            )

    return point_detectors, area_detectors
