import os
import sys
from typing import Optional

from clockwork.signal_group_controller import PhaseRingController
from simengine.confread_integrated import GlobalConf as SystemConf
from simengine.detector import (
    DetectorConf,
    E1Reading,
    E3Reading,
)
from simengine.logger import SimLogger
from simengine.timer import Timer, create_timer_from_conf

from .sumo import simulation_is_finished, start_simulation

SUMO_HOME = os.environ.get("SUMO_HOME")
if SUMO_HOME is None:
    sys.exit('please declare environment variable "SUMO_HOME"')

SUMO_TOOLS = os.path.join(os.environ["SUMO_HOME"], "tools")
sys.path.append(SUMO_TOOLS)
import traci


class SimEngine:
    """
    SimEngine is a class for running simulation within Optimus. It differs from
    the original Simengine of OC by being able to run simulation in multiple steps.
    This allows for the configuring of the signal controller while keeping the simulation running.
    """

    def __init__(
        self,
        conf: SystemConf,
        logger: Optional[SimLogger] = None,
    ) -> None:
        self.traci = traci  # Open TraCI connection
        self.conf = conf  # System configuration for simulation
        self.logger: Optional[SimLogger] = logger

        # System timer for ticking simulation
        self._timer: Timer = create_timer_from_conf(conf.cnf)
        self._timer.reset()

        # Signal controller is created
        self._controller: PhaseRingController = PhaseRingController(
            conf.cnf, self._timer
        )
        self._controller.set_sumo_outputs(self.conf.cnf["sumo"]["group_outputs"])

        if self.logger is not None:
            self.logger.log("Starting Sumo simulation in a background process...")
        # SUMO simulation is started.
        # Open TraCI connection is used to communicate with the simulation
        self._start_traci()

        self._cur: int = 0  # Current step
        self.teleported: int = 0  # Number of teleported vehicles

        # Detector configuration for SUMO
        self._det_conf = DetectorConf(self._controller, self.traci)

    def reset(self) -> None:
        """
        reset is a function for resetting the simulation and its timer.
        This is roughly equal to creating a new instance of SimEngine.
        """
        self._timer.reset()
        self.close()
        self._start_traci()

    def close(self) -> None:
        if self.logger is not None:
            self.logger.log("Closing TraCI")
        if self.traci.isLoaded():
            self.traci.close(False)
        else:
            print("TraCI was not loaded!!")

    def run(self, steps: int = -1) -> None:
        """
        run is a function for running a traffic simulation with Open Controller.
        It differs from the original Simengine by allowing for paused and
        continued running of simulations. This is useful for Optimus as it needs
        to run simulations for shorter sessions and change the controller
        configurations in between sessions.

        @param:
        steps: int = number of simulation steps to advance the actual Sumo
        simulation. If not provided, will run indefinetely or until simulation ends.

        @return:
        None
        """
        if self.logger is not None:
            self.logger.log("Starting simulation...")
        sumo_name = self.conf.cnf["controller"]["sumo_name"]
        cur: int = 0

        while not self._is_simulation_finished(cur, steps):
            for vehicleId in self.traci.vehicle.getIDList():
                self.traci.vehicle.setSpeedMode(
                    vehicleId, 55
                )  # disable right of way check, vehicles can enter the junction, despite queue end

            self._det_conf.sumo_e1detections_to_controller()
            self._det_conf.sumo_e3detections_to_controller()

            self._controller.tick()

            states = self._controller.get_sumo_states()
            ocTLScount = len(states)
            sumo_tls = self.traci.trafficlight.getControlledLinks(sumo_name)
            SumoTLScount = len(sumo_tls)
            if ocTLScount < SumoTLScount:
                states = "r" + states  # DBIK20250129 add group 0 ?
            try:
                self.traci.trafficlight.setRedYellowGreenState(sumo_name, states)
            except:
                print(
                    "Error in signal counts: OC count: ",
                    ocTLScount,
                    "Sumo TLS: ",
                    SumoTLScount,
                )

            try:
                self.traci.simulationStep()
            except self.traci.exceptions.FatalTraCIError:
                print("Fatal error in sumo, exiting")
                break

            if self.traci.simulation.getStartingTeleportNumber():
                self.teleported += 1

            self._timer.tick()  # DBIK230711 timer tick only in the main loop

            cur += 1
            self._cur += 1

        if self.logger is not None:
            self.logger.log("Simulation stopped")

    def _is_simulation_finished(
        self, current_steps: int, target_steps: int = -1
    ) -> bool:
        if target_steps > 0 and current_steps >= target_steps:
            return True
        return simulation_is_finished(self.traci, self._timer)

    def _start_traci(self) -> None:
        try:
            start_simulation(self.traci, self.conf.cnf["sumo"]["file_name"])
        except Exception as e:
            print("Sumo start failed:", e)
            return

    def update_controller(self, new: SystemConf) -> None:
        self._controller = PhaseRingController(new.cnf, self._timer)

    def get_current_simulation_time(self) -> float:
        """
        get_current_simulation_time returns the current time in seconds
        """
        return self._timer.seconds

    def get_detector_readings(self) -> tuple[list[E1Reading], list[E3Reading]]:
        """
        get_detector_readings returns all readings from both e1 and e3 detectors in the simulation

        @return:
        list[E1Reading] = list of e1 detector readings from all e1 detectors
        list[E3Reading] = list of e3 detector readings from all e3 detectors
        """
        e1_ids: list[str] = self._det_conf.sumo_loops
        e3_ids: list[str] = self._det_conf.sumo_e3dets

        e1_readings: list[E1Reading] = []
        e3_readings: list[E3Reading] = []

        for det_id in e1_ids:
            e1: E1Reading = self._det_conf.get_e1_readings(det_id)
            e1_readings.append(e1)

        for det_id in e3_ids:
            e3: E3Reading = self._det_conf.get_e3_readings(det_id)
            e3_readings.append(e3)

        return e1_readings, e3_readings
