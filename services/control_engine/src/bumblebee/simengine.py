import libsumo

from services.control_engine.src.detectors.area_detector import AreaDetector
from services.control_engine.src.detectors.sumo_e2_detector import E2AreaDetector
from services.control_engine.src.detectors.sumo_e3_detector import E3AreaDetector

from .configuration import SimEngineConf

SUMO_BIN = "sumo"


class SimEngine:
    """SimEngine is a simulation runner that is designed to work in RL applications.
    It can run simulations in steps to allow for neural network training which
    requires fine grained control over environment. SimEngine is designed to be
    used through Bumblebee's TrafficEnv environment. SimEngine can run in both
    headless and GUI mode to allow for quick training and visual debugging with the
    same environment.
    """

    def __init__(self, conf: SimEngineConf) -> None:
        self._sumo_file = conf.sumo_file
        self._detectors: list[AreaDetector] = []
        for detector_conf in conf.detector_confs:
            detector: AreaDetector | None = None
            detector_type: str = detector_conf[0]
            detector_sumo_id: str = detector_conf[1]
            if detector_type == "e2_detector":
                detector = E2AreaDetector(detector_sumo_id)
            elif detector_type == "e3_detector":
                detector = E3AreaDetector(detector_sumo_id)
            else:
                raise ValueError(
                    "Unknown detector type for detector "
                    f"{detector_sumo_id}: {detector_type}"
                )
            self._detectors.append(detector)

    def reset(self) -> None:
        """Reset the simulation to its original state."""
        try:
            libsumo.load([SUMO_BIN, "-c", self._sumo_file, "--start", "--quit-on-end"])
        except Exception:
            libsumo.start([SUMO_BIN, "-c", self._sumo_file, "--start", "--quit-on-end"])

    def step(self, time_step_count: int) -> None:
        """Advance the simulation by specified time steps."""

        for _ in range(time_step_count):
            libsumo.simulationStep()

    def close(self) -> None:
        libsumo.close()

    def set_signal_group_states(
        self, signal_controller_id: str, new_states: str
    ) -> None:
        libsumo.trafficlight.setRedYellowGreenState(signal_controller_id, new_states)

    def get_detector_readings(self) -> list[dict[str, float]]:
        """Get detector readings from area detectors.

        Returns:
            Traffic state as a list of dictionaries
                where the key is the parameter name.
        """

        # TODO: We should subscribe to the detector data
        # rather than retrieve it individually every step.

        readings: list[dict[str, float]] = []
        for detector in self._detectors:
            reading: dict[str, float] = {
                "vehicle_count": detector.vehicle_count(),
                "average_speed": detector.average_speed(),
                "average_time_loss": detector.average_time_loss(),
            }
            readings.append(reading)

        return readings

    def get_teleported(self) -> list[str]:
        """Get IDs of vehicles that teleported in the last step.

        Returns:
            List of vehicle IDs that have teleported during the last step.
        """

        return libsumo.vehicle.getTeleportingIDList()

    def get_step_length(self) -> float:
        return libsumo.simulation.getDeltaT()
