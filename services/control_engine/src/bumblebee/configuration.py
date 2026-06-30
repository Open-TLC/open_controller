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

        self.controllers: list[ControllerConf] = []

        # Support for multiple controller configurations.
        controller_confs: list[dict[str, Any]] | None = conf.get("controllers")
        if controller_confs is not None and len(controller_confs) > 0:
            for controller_conf in controller_confs:
                self.controllers.append(ControllerConf(controller_conf))

        # Support for single controller configurations.
        controller_conf: dict[str, Any] | None = conf.get("controller")
        if controller_conf is not None:
            self.controllers.append(ControllerConf(controller_conf))


class TrafficEnvConf:
    def __init__(self, conf: dict[str, Any]) -> None:
        # Whether to run in multi agent or single agent mode.
        # Defaults to single agent mode.
        val = conf.get("multi_agent")
        self.multi_agent: bool = bool(val) if val is not None else False

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


class ControllerConf:
    """Configuration for a single controller.

    This can mean a "production" controller
    or a controller used in training.
    """

    def __init__(self, conf: dict[str, Any]) -> None:
        self.name: str = conf["sumo_name"]

        self.group_outputs: list[int] = conf["group_outputs"]

        self.intergreens: list[list[float]] = conf["intergreens"]

        self.detector_confs: list[AreaDetectorConfiguration] = []
        for det_conf in conf["detectors"]:
            self.detector_confs.append(AreaDetectorConfiguration(det_conf))
