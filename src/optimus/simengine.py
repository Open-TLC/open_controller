import os
import sys
from dataclasses import dataclass
from typing import Any, Optional

from clockwork.signal_group_controller import PhaseRingController
from simengine.confread_integrated import GlobalConf as SystemConf
from simengine.detector import (
    DetectorConf,
    E1Reading,
    E3Reading,
)
from simengine.logger import SimLogger
from simengine.timer import Timer, create_timer_from_conf

from .sumo import Trip, TripReader, simulation_is_finished, start_simulation

SUMO_HOME = os.environ.get("SUMO_HOME")
if SUMO_HOME is None:
    sys.exit('please declare environment variable "SUMO_HOME"')

SUMO_TOOLS = os.path.join(os.environ["SUMO_HOME"], "tools")
sys.path.append(SUMO_TOOLS)
# libsumo provides the same function signatures as TraCI but with lower latencies.
# Main limitation is that libsumo can't be used with SUMO's gui. As this is not
# an objective with Optimus's simengine, libsumo can be used here without any
# drawbacks to reduce training time in the model training loop.
import libsumo as traci


class SimEngine:
    """
    SimEngine is a class for running simulation within Optimus. It differs from
    the original Simengine of OC by being able to run simulation in multiple steps.
    This allows for the configuring of the signal controller while keeping the simulation running.
    """

    def __init__(
        self,
        model_root: str,
        logger: Optional[SimLogger] = None,
        collect_time_loss: bool = False,
    ) -> None:
        self.traci = traci  # Open TraCI connection
        self._model_root = model_root
        conf = SystemConf(os.path.join(model_root, "contr", "e3.json"))
        self.conf = conf  # System configuration for simulation
        self.logger: Optional[SimLogger] = logger

        # System timer for ticking simulation
        self._timer: Timer = create_timer_from_conf(conf.cnf)
        self._timer.reset()

        # Signal controller is created
        self._controller = PhaseRingController(conf.cnf, self._timer)
        self._controller.set_sumo_outputs(self.conf.cnf["sumo"]["group_outputs"])

        if self.logger is not None:
            self.logger.log("Starting Sumo simulation in a background process...")
        # SUMO simulation is started.
        # Open TraCI connection is used to communicate with the simulation
        self._start_traci()

        self.teleported: int = 0  # Number of teleported vehicles

        # Detector configuration for SUMO
        self._det_conf = DetectorConf(self._controller, self.traci)

        # Parser used to read tripinfo from a file
        self._init_tripinfo_parser()

        # Should the simulation engine collect time losses when running simulation
        self._collect_time_loss = collect_time_loss

        # Dict of finished trips with vehicle ID as key
        self._finished_vehicles: dict[str, Trip] = {}
        # List of time losses from last running session
        self.last_run_losses: list[float] = []

        self.last_run_e1_detections: dict[str, E1ReadingOverTime] = {}
        self.last_run_e3_detections: dict[str, E3ReadingOverTime] = {}
        self._reset_last_run_detections()

    def reset(self) -> None:
        """
        reset is a function for resetting the simulation and its timer.
        This is roughly equal to creating a new instance of SimEngine.
        """
        self._timer.reset()
        self.close()
        self._start_traci()
        self.teleported = 0
        self._controller = PhaseRingController(self.conf.cnf, self._timer)
        self._init_tripinfo_parser()
        self._reset_last_run_detections()

    def close(self) -> None:
        if self.logger is not None:
            self.logger.log("Closing TraCI")
        if self.traci.isLoaded():
            self.traci.close()
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

        # This reset's the list of time lossses for the run
        self.last_run_losses: list[float] = []

        self._reset_last_run_detections()

        while not self._is_simulation_finished(cur, steps):
            for vehicleId in self.traci.vehicle.getIDList():
                self.traci.vehicle.setSpeedMode(
                    vehicleId, 55
                )  # disable right of way check, vehicles can enter the junction, despite queue end

            self._det_conf.sumo_e1detections_to_controller()
            self._det_conf.sumo_e3detections_to_controller()

            new_e1, new_3 = self.get_detector_readings()
            for id in new_e1.keys():
                prev = self.last_run_e1_detections.get(id)
                if not prev:
                    prev = E1ReadingOverTime(0, 0)
                prev.vehicle_count += new_e1[id][0]

                prev.total_occupancy += new_e1[id][1]
                prev.index += 1
                self.last_run_e1_detections[id] = prev

            for id in new_3.keys():
                prev = self.last_run_e3_detections.get(id)
                if not prev:
                    prev = E3ReadingOverTime(0, 0)

                prev.total_vehicle_count += new_3[id][0]
                prev.total_transit_count += new_3[id][1]

                prev.index += 1
                self.last_run_e3_detections[id] = prev

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

            if self._collect_time_loss:
                current_step_losses: list[float] = self._retrieve_arrived_time_losses()
                self.last_run_losses.extend(current_step_losses)

            self.teleported += self.traci.simulation.getStartingTeleportNumber()

            self._timer.tick()  # DBIK230711 timer tick only in the main loop

            cur += 1

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

    def update_controller_extenders(self, new: SystemConf) -> None:
        self.conf = new  # SimEngine's own configuration is updated

        extender_conf: dict[str, Any] = new.cnf["controller"]["extenders"]
        for extender_id in extender_conf.keys():
            extender_group = extender_conf[extender_id]["group"]
            for extender in self._controller.e3extenders:
                if extender_group == extender.group.group_name:
                    new_threshold: float = extender_conf[extender_id]["ext_threshold"]
                    # avoids always extending the green in extension algorithm
                    if new_threshold == 0:
                        new_threshold = 0.1
                    extender.ext_threshold = new_threshold

                    new_discount: float = extender_conf[extender_id]["time_discount"]
                    # avoids "divide by zero" cases
                    if new_discount == 0:
                        new_discount = 0.1
                    extender.time_discount = new_discount

    def get_current_simulation_time(self) -> float:
        """
        get_current_simulation_time returns the current time in seconds
        """
        return self._timer.seconds

    def get_detector_readings(
        self,
    ) -> tuple[dict[str, E1Reading], dict[str, E3Reading]]:
        """
        get_detector_readings returns all readings from both e1 and e3 detectors in the simulation

        @return:
        dict[str, E1Reading] = dictionary of e1 detector readings from all e1 detectors with detector ID as the key
        dict[str, E3Reading] = dictionary of e3 detector readings from all e3 detectors with detector ID as the key
        """
        e1_ids: list[str] = self._det_conf.sumo_loops
        e3_ids: list[str] = self._det_conf.sumo_e3dets

        e1_readings: dict[str, E1Reading] = {}
        e3_readings: dict[str, E3Reading] = {}

        for det_id in e1_ids:
            e1: E1Reading = self._det_conf.get_e1_readings(det_id)
            e1_readings[det_id] = e1

        for det_id in e3_ids:
            e3: E3Reading = self._det_conf.get_e3_readings(det_id)
            e3_readings[det_id] = e3

        return e1_readings, e3_readings

    def _init_tripinfo_parser(self) -> None:
        tripinfo_filepath = os.path.join(
            self._model_root, "out", "1J_tripinfo.trip.xml"
        )
        self._tripinfo_parser = TripReader(tripinfo_filepath)

    def _retrieve_arrived_time_losses(self) -> list[float]:
        time_losses: list[float] = []

        veh_ids = self.traci.simulation.getArrivedIDList()
        if len(veh_ids) == 0:
            return []
        new_trips = self._tripinfo_parser.get_new_trips()
        for veh_id in veh_ids:
            trip = new_trips.get(veh_id)
            if trip is None:
                print(f"no trip found for vehicle ID {veh_id}")
                continue
            time_losses.append(trip.time_loss)

            # Finished trip is added to dictionary for later use
            self._finished_vehicles[veh_id] = trip
        return time_losses

    def _reset_last_run_detections(self) -> None:
        for det_id in self._det_conf.sumo_loops:
            self.last_run_e1_detections[det_id] = E1ReadingOverTime(0, 0)

        for det_id in self._det_conf.sumo_e3dets:
            self.last_run_e3_detections[det_id] = E3ReadingOverTime(0, 0)

    @property
    def total_time_loss(self) -> float:
        res: float = 0
        count: int = len(self._finished_vehicles.keys())
        print(f"trips in total: {count}")
        for trip in self._finished_vehicles.values():
            res += trip.time_loss
        print(f"avg loss: {round(res / count, 3)}")
        return res

    @property
    def last_run_total_time_loss(self) -> float:
        return sum(self.last_run_losses)


@dataclass
class E1ReadingOverTime:
    vehicle_count: int
    total_occupancy: float
    index: int = 0

    @property
    def average_occupancy(self) -> float:
        if self.index == 0:
            return 0
        return self.total_occupancy / self.index


@dataclass
class E3ReadingOverTime:
    total_vehicle_count: int
    total_transit_count: int
    index: int = 0

    @property
    def average_vehicle_count(self) -> float:
        if self.index == 0:
            return 0
        return self.total_vehicle_count / self.index

    @property
    def average_transit_count(self) -> float:
        if self.index == 0:
            return 0
        return self.total_transit_count / self.index
