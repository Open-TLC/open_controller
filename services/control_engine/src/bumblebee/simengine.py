import libsumo

from .configuration import SimEngineConf


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

    def reset(self) -> None:
        """Reset the simulation to its original state."""
        sumo_args = [
            "-c",
            self._sumo_file,
            "--quit-on-end",
            "--no-warnings",
            "--step-length",
            "0.1",
        ]
        try:
            libsumo.load(sumo_args)
        except Exception as e:
            print(f"Error restarting SUMO {e}")
            libsumo.start(sumo_args)

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

    def get_teleported(self) -> list[str]:
        """Get IDs of vehicles that teleported in the last step.

        Returns:
            List of vehicle IDs that have teleported during the last step.
        """

        return libsumo.vehicle.getTeleportingIDList()

    def get_step_length(self) -> float:
        delta_t = libsumo.simulation.getDeltaT()
        return delta_t

    def get_simulation_time(self) -> float:
        return libsumo.simulation.getTime()
