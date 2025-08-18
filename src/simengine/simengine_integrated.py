# -*- coding: utf-8 -*-
"""The sumo interface module

This module operates Sumo simulator and applies controller to it
This is an integrated version that doesn't use NATS
"""
#
# Open Controller, an open source traffic signal control platform
# URL: https://www.opencontroller.org
# Copyright 2023 - 2024 by Conveqs Oy, Kari Koskinen and others
# This program has been released under EUPL-1.2 license which is available at
# URL: https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12
#

import os
import sys
import time
from typing import Optional

from clockwork.signal_group_controller import PhaseRingController
from optimus.sumo import simulation_is_finished

from .confread_integrated import GlobalConf
from .detector import (
    DetectorConf,
)
from .logger import SimLogger
from .timer import Timer, create_timer_from_conf

# Alternatively:
# we need to import python modules from the $SUMO_HOME/tools directory
SUMO_HOME = os.environ.get("SUMO_HOME")
if SUMO_HOME is None:
    sys.exit('please declare environment variable "SUMO_HOME"')

SUMO_TOOLS = os.path.join(os.environ["SUMO_HOME"], "tools")
sys.path.append(SUMO_TOOLS)
import traci

sumo_bin_path = os.path.join(SUMO_HOME, "bin")
# Add the sumo/bin directory to the PATH for this process
if os.path.isdir(sumo_bin_path) and sumo_bin_path not in os.environ["PATH"].split(
    os.pathsep
):
    os.environ["PATH"] = sumo_bin_path + os.pathsep + os.environ["PATH"]

# Simulation configuration to be used can be set here
MODEL_ROOT = "models/test"

# Note these are not in use at sig-group
SUMO_BIN_NAME = "sumo"
SUMO_BIN_NAME_GRAPH = "sumo-gui"


# We run the sumo model based on conf dictionery given as parameter
def run_sumo(conf_filename: str):
    """Run sumo with given configuration"""
    print("Running sumo with conf", conf_filename)
    unit_cnf = GlobalConf(filename=conf_filename)

    sys_cnf = unit_cnf.cnf

    system_timer = create_timer_from_conf(sys_cnf)

    traffic_controller = PhaseRingController(sys_cnf, system_timer)

    # We override the outputs if given in conf
    if "group_outputs" in sys_cnf["sumo"].keys():
        sumo_outputs = sys_cnf["sumo"]["group_outputs"]
        # print("We override the sumo outputs from conf with:", sumo_outputs)
        traffic_controller.set_sumo_outputs(sumo_outputs, verbose=False)

    # Graph always if set in conf, and also if param says so
    if sys_cnf["sumo"]["graph"]:
        sumo_bin = SUMO_BIN_NAME_GRAPH
    else:
        sumo_bin = SUMO_BIN_NAME

    # Conf is defined in sumo section of conf
    sumo_file = sys_cnf["sumo"]["file_name"]
    try:
        traci.start([sumo_bin, "-c", sumo_file, "--start", "--quit-on-end"])
    except Exception as e:
        print("Sumo start failed:", e)
        return

    detector_conf = DetectorConf(traffic_controller, traci_connection=traci)

    # Start the actual simulation
    system_timer.reset()

    start_simulation(sys_cnf, system_timer, traffic_controller, detector_conf)

    print("Closing traci")
    try:
        traci.close(False)
    except Exception as e:
        print("Traci closed failed:", e)
    sys.stdout.flush()


def print_det_status():
    loopcount = traci.inductionloop.getIDCount()
    loops = traci.inductionloop.getIDList()
    print("Found {} loops: {}".format(loopcount, loops))
    for loop_id in loops:
        lane = traci.inductionloop.getLaneID(loop_id)
        avg_speed = traci.inductionloop.getLastStepMeanSpeed(loop_id)
        occupancy = traci.inductionloop.getLastStepOccupancy(loop_id)
        print("lane:{}, a_speed:{}, occupancy:{}".format(lane, avg_speed, occupancy))


def start_simulation(
    cnf: dict,
    timer: Timer,
    controller: PhaseRingController,
    det_conf: DetectorConf,
    logger: Optional[SimLogger] = None,
):
    real_time = timer.real_seconds  # DBIK230713
    next_update_time = real_time  # DBIK230713
    SUMOSIM = True

    sumo_name = cnf["controller"]["sumo_name"]

    while not simulation_is_finished(traci, timer=timer):
        cycle_start = time.time()
        for vehicleId in traci.vehicle.getIDList():
            traci.vehicle.setSpeedMode(
                vehicleId, 55
            )  # disable right of way check, vehicles can enter the junction, despite queue end

        real_time = timer.real_seconds  # DBIK230711

        if timer.mode == "real":
            time.sleep(0.01)  # DBIK230711
            timer.sleep_tick()
            real_time = timer.real_seconds  # DBIK230711

        next_update_time = next_update_time + timer.time_step  # DBIK230720

        if SUMOSIM:
            det_conf.sumo_e1detections_to_controller()
            det_conf.sumo_e3detections_to_controller()

        controller.tick()

        if logger is not None:
            statusstring = controller.get_control_status()
            logger.log_status(statusstring, timer.steps, timer.str_seconds())

        states = controller.get_sumo_states()
        ocTLScount = len(states)
        sumo_tls = traci.trafficlight.getControlledLinks(sumo_name)
        SumoTLScount = len(sumo_tls)
        if ocTLScount < SumoTLScount:
            states = "r" + states  # DBIK20250129 add group 0 ?
        try:
            traci.trafficlight.setRedYellowGreenState(sumo_name, states)
        except:
            print(
                "Error in signal counts: OC count: ",
                ocTLScount,
                "Sumo TLS: ",
                SumoTLScount,
            )

        try:
            traci.simulationStep()
        except traci.exceptions.FatalTraCIError:
            print("Fatal error in sumo, exiting")
            break

        timer.tick()  # DBIK230711 timer tick only in the main loop

        if logger is not None:
            cycle_end = time.time()
            cycle_dur_ms = (cycle_end - cycle_start) * 1000
            logger.log(f"Cycle took: {cycle_dur_ms} milliseconds")


if __name__ == "__main__":
    run_sumo(os.path.join(MODEL_ROOT, "contr/e3.json"))
