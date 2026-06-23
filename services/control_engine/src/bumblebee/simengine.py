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
        if conf.step_length <= 0:
            raise ValueError(f"Step length ({conf.step_length}) must be greater than 0")
        self._step_length = conf.step_length
        self._sumo_running: bool = False

    def reset(self) -> None:
        """Reset the simulation to its original state."""

        sumo_args = [
            "sumo",
            "-c",
            self._sumo_file,
            "--quit-on-end",
            "--no-warnings",
            "--step-length",
            str(self._step_length),
        ]

        try:
            if not self._sumo_running:
                libsumo.start(sumo_args)
                self._sumo_running = True
            else:
                # If SUMO is already running, the executable name is skipped.
                libsumo.load(sumo_args[1:])
        except Exception as e:
            raise libsumo.FatalTraCIError(f"Starting SUMO failed: {e}")

    def step(self, time_step_count: int) -> None:
        """Advance the simulation by specified time steps."""

        for _ in range(time_step_count):
            libsumo.simulationStep()

    def close(self) -> None:
        libsumo.close()
        self._sumo_running = False

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

    @property
    def step_length(self) -> float:
        return self._step_length

    def get_simulation_time(self) -> float:
        return libsumo.simulation.getTime()
