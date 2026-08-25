from nats.aio.client import Client

from services.control_engine.src.detectors.traffic_indicators_area_detector import (
    TrafficIndicatorsAreaDetector,
)

from .area_detector import AreaDetector
from .point_detector import PointDetector
from .sumo_e1_detector import E1PointDetector, E1TransitPointDetector
from .sumo_e2_detector import E2AreaDetector, E2TransitAreaDetector
from .sumo_e3_detector import E3AreaDetector, E3TransitAreaDetector

SUPPORTED_DETECTOR_TYPES = [
    "e1_detector",
    "e2_detector",
    "e3_detector",
    "traffic_indicators_detector",
    "e1_transit_detector",
    "e2_transit_detector",
    "e3_transit_detector",
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
            point_detectors.append(E1PointDetector(conf.id))

        elif conf.type == SUPPORTED_DETECTOR_TYPES[1]:
            area_detectors.append(E2AreaDetector(conf.id))

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

        elif conf.type == SUPPORTED_DETECTOR_TYPES[4]:
            point_detectors.append(E1TransitPointDetector(conf.id))

        elif conf.type == SUPPORTED_DETECTOR_TYPES[5]:
            area_detectors.append(E2TransitAreaDetector(conf.id))

        elif conf.type == SUPPORTED_DETECTOR_TYPES[6]:
            area_detectors.append(E3TransitAreaDetector(conf.id))

    return point_detectors, area_detectors
