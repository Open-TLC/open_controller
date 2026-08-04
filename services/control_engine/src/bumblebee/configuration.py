from typing import Any

import numpy as np

from services.control_engine.src.detectors.configuration import DetectorConfiguration
from services.control_engine.src.geometry.junction_geometry import JunctionGeometry


class TrainerConf:
    def __init__(self, raw_conf: dict[str, Any]) -> None:
        self.total_steps: int = raw_conf["training_steps"]
        self.traffic_env = TrafficEnvConf(raw_conf["traffic_env"])
        self.simengine = SimEngineConf(raw_conf["simengine"])

        raw_controller_confs: list[dict[str, Any]] | None = raw_conf.get("controllers")
        if raw_controller_confs is None or len(raw_controller_confs) == 0:
            raise ValueError(
                "No controllers configured. Configure at "
                "least 1 controller to train Bumblebee.",
            )

        self.controllers: list[BumblebeeControllerConf] = []

        for raw_controller_conf in raw_controller_confs:
            controller_id = raw_controller_conf["id"]
            controller_options = raw_controller_conf["options"]
            self.controllers.append(
                BumblebeeControllerConf(controller_id, controller_options),
            )

        self.algorithm: str = self.controllers[0].algorithm

        raw_detector_confs: list[dict[str, Any]] | None = raw_conf.get("detectors")
        if raw_detector_confs is None or len(raw_detector_confs) == 0:
            raise ValueError(
                "No detectors configured. Configure at "
                "least 1 detector to train Bumblebee.",
            )

        self.detectors: list[DetectorConfiguration] = []

        for raw_detector_conf in raw_detector_confs:
            self.detectors.append(DetectorConfiguration(raw_detector_conf))


class TrafficEnvConf:
    def __init__(self, conf: dict[str, Any]) -> None:
        self.episode_steps: int = int(conf["episode_steps"])

        # Length of a training step in seconds.
        # Defaults to 1 s.
        val = conf.get("step_length")
        self.step_length: float = float(val) if val is not None else 1.0


class SimEngineConf:
    """Configuration for Bumblebee's simulation engine."""

    def __init__(self, conf: dict[str, Any]) -> None:
        self.sumo_file: str = conf["sumo_file"]
        # Length of a simulation step in seconds.
        # Defaults to 0.1 s.
        val = conf.get("step_length")
        self.step_length: float = float(val) if val is not None else 0.1


DEFAULT_VEHICLE_VEHICLE_INTERGREEN: float = 3
DEFAULT_VEHICLE_PEDESTRIAN_INTERGREEN: float = 1
DEFAULT_PEDESTRIAN_VEHICLE_INTERGREEN: float = 10


class BumblebeeControllerConf:
    """Configuration for a Bumblebee controller.

    This can mean a "production" controller
    or a controller used in training.
    """

    def __init__(self, controller_id: str, raw_options: dict[str, Any]) -> None:
        self.id = controller_id
        self.model_file = raw_options["model_file"]
        self.algorithm = raw_options["algorithm"]

        self.geometry = JunctionGeometry(controller_id, raw_options)
        self.conflict_matrix: np.ndarray = self.geometry.generate_conflict_matrix()

        # Map conflict types to intergreen times.
        vv = raw_options.get(
            "vehicle_vehicle_intergreen",
            DEFAULT_VEHICLE_VEHICLE_INTERGREEN,
        )
        vp = raw_options.get(
            "vehicle_pedestrian_intergreen",
            DEFAULT_VEHICLE_PEDESTRIAN_INTERGREEN,
        )
        pv = raw_options.get(
            "pedestrian_vehicle_intergreen",
            DEFAULT_PEDESTRIAN_VEHICLE_INTERGREEN,
        )
        intergreen_mapping = np.array([0, vv, pv, vp])
        self.intergreens: np.ndarray = intergreen_mapping[self.conflict_matrix]

        self.transit_links: list[str] = [
            f"{self.id}.{link_id}" for link_id in raw_options.get("transit_links", [])
        ]
