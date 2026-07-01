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

        # Metric tracking variables
        self._num_teleported_last_step: int = 0
        self._finished_travel_time_last_step: float = 0.0
        self._finished_vehicles_count_last_step: int = 0

        # State tracking memory to map: { vehicle_id: departure_simulation_time }
        self._departure_times: dict[str, float] = {}

    def reset(self) -> None:
        """Reset the simulation to its original state."""
        self._num_teleported_last_step = 0
        self._finished_travel_time_last_step = 0.0
        self._finished_vehicles_count_last_step = 0
        self._departure_times.clear()

        sumo_args = [
            "sumo",
            "-c",
            self._sumo_file,
            "--quit-on-end",
            "--no-warnings",
            "--step-length",
            str(self._step_length),
            "--time-to-teleport",
            "120",
        ]

        if not self._sumo_running:
            libsumo.start(sumo_args)
            self._sumo_running = True
        else:
            # If SUMO is already running, the executable name is skipped.
            libsumo.load(sumo_args[1:])

        current_time = libsumo.simulation.getTime()
        for veh_id in libsumo.vehicle.getIDList():
            try:
                self._departure_times[veh_id] = libsumo.vehicle.getDeparture(veh_id)
            except Exception:
                self._departure_times[veh_id] = current_time

    def step(self, time_step_count: int) -> None:
        """Advance the simulation by specified time steps."""
        self._num_teleported_last_step = 0
        self._finished_travel_time_last_step = 0.0
        self._finished_vehicles_count_last_step = 0

        for _ in range(time_step_count):
            libsumo.simulationStep()
            current_time = libsumo.simulation.getTime()

            self._num_teleported_last_step += (
                libsumo.simulation.getStartingTeleportNumber()
            )

            for veh_id in libsumo.simulation.getDepartedIDList():
                self._departure_times[veh_id] = current_time

            for veh_id in libsumo.simulation.getArrivedIDList():
                if veh_id in self._departure_times:
                    depart_time = self._departure_times.pop(veh_id)
                    travel_time = current_time - depart_time

                    self._finished_travel_time_last_step += travel_time
                    self._finished_vehicles_count_last_step += 1

    def close(self) -> None:
        libsumo.close()
        self._sumo_running = False

    def set_signal_group_states(
        self,
        signal_controller_id: str,
        new_states: str,
    ) -> None:
        libsumo.trafficlight.setRedYellowGreenState(signal_controller_id, new_states)

    @property
    def get_teleported_count(self) -> int:
        """Get the number of vehicles that teleported in the last step.

        Returns:
            Number of vehicle that have teleported during the last step.

        """
        return self._num_teleported_last_step

    @property
    def get_finished_travel_time(self) -> float:
        """Get the total accumulated travel time of vehicles that finished in the last step."""
        return self._finished_travel_time_last_step

    @property
    def get_finished_vehicles_count(self) -> int:
        """Get the total number of vehicles that finished in the last step."""
        return self._finished_vehicles_count_last_step

    @property
    def step_length(self) -> float:
        return self._step_length

    def get_simulation_time(self) -> float:
        return libsumo.simulation.getTime()
