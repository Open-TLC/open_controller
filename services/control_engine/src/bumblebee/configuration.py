from typing import Any


class TrafficEnvConf:
    def __init__(self, conf: dict[str, Any]) -> None:
        self.sumo_name: str = str(conf["sumo_name"])
        self.simulation_step_count: int = int(conf["simulation_step_count"])
        self.intergreens: list[list[float]] = conf["intergreens"]


class SimEngineConf:
    def __init__(self, conf: dict[str, Any]) -> None:
        self.sumo_file: str = conf["sumo_file"]
        self.detector_confs: list[tuple[str, str]] = conf["detectors"]
