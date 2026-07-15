SUPPORTED_DETECTOR_TYPES = ["e1_detector", "e2_detector", "e3_detector"]


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
