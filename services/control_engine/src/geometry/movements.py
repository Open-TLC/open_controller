from dataclasses import dataclass

from services.control_engine.src.detectors.area_detector import AreaDetector


@dataclass
class DownstreamMovement:
    """Represents a downstream movement from an incoming node."""

    downstream_node_id: str
    detector: AreaDetector
    theta: float


@dataclass
class LanePressureConfig:
    """Represents an incoming node and its downstream targets."""

    node_id: str
    incoming_detector: AreaDetector
    movements: list[DownstreamMovement]
