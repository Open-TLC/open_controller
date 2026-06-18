import libsumo

SUMO_BIN = "sumo"


class SimEngine:
    """SimEngine is a simulation runner that is designed to work in RL applications.
    It can run simulations in steps to allow for neural network training which
    requires fine grained control over environment. SimEngine is designed to be
    used through Bumblebee's TrafficEnv environment. SimEngine can run in both
    headless and GUI mode to allow for quick training and visual debugging with the
    same environment.
    """

    def __init__(self, sumo_file: str) -> None:
        self._sumo_file = sumo_file

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

    def get_traffic_state(self) -> dict[str, dict[str, float]]:
        """Get the current traffic state in simulation.

        Returns:
            Traffic state as a dictionary of dictionaries. The first key
                is the area ID and the second key is the parameter name.
        """

        # TODO: We should subscribe to the detector data
        # rather than retrieve it individually every step.

        raise NotImplementedError

    def get_wait_times(self, vehicle_ids: list[str]) -> list[float]:
        """Get time losses experienced by specified vehicles.

        Args:
            vehicle_ids: List of vehicle IDs to get.

        Returns:
            List of time losses by vehicle. The order of vehicles is persisted.
        """

        return [float(libsumo.vehicle.getTimeLoss(veh_id)) for veh_id in vehicle_ids]

    def get_teleported(self) -> list[str]:
        """Get IDs of vehicles that teleported in the last step.

        Returns:
            List of vehicle IDs that have teleported during the last step.
        """

        return libsumo.vehicle.getTeleportingIDList()

    def get_step_length(self) -> float:
        return libsumo.simulation.getDeltaT()
