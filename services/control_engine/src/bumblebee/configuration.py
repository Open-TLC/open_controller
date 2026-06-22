from typing import Any

from services.control_engine.src.detectors.configuration import (
    AreaDetectorConfiguration,
)


class TrainerConf:
    def __init__(self, conf: dict[str, Any]) -> None:
        self.algorithm: str = conf["algorithm"]
        self.total_steps: int = conf["training_steps"]
        self.traffic_env = TrafficEnvConf(conf["traffic_env"])
        self.simengine = SimEngineConf(conf["simengine"])


class TrafficEnvConf:
    def __init__(self, conf: dict[str, Any]) -> None:
        self.episode_steps: int = int(conf["episode_steps"])
        self.sumo_name: str = str(conf["sumo_name"])
        self.simulation_step_count: int = int(conf["simulation_step_count"])
        self.intergreens: list[list[float]] = conf["intergreens"]

        self.detector_confs: list[AreaDetectorConfiguration] = []
        for det_conf in conf["detectors"]:
            self.detector_confs.append(AreaDetectorConfiguration(det_conf))


class SimEngineConf:
    def __init__(self, conf: dict[str, Any]) -> None:
        self.sumo_file: str = conf["sumo_file"]


class BumblebeeControllerConf:
    def __init__(self, conf: dict[str, Any]) -> None:
        self.algorithm = conf["algorithm"]
        self.model_path = conf["model_path"]

        # Length of a tick in seconds.
        self.step_length: float = float(conf["step_length"])

        self.intergreens: list[list[float]] = conf["intergreens"]

        self.detector_confs: list[AreaDetectorConfiguration] = []
        for det_conf in conf["detectors"]:
            self.detector_confs.append(AreaDetectorConfiguration(det_conf))
