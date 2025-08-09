import json
import subprocess
import sys
import typing
import xml.etree.ElementTree as et
from dataclasses import dataclass
from typing import Optional

from simengine.timer import Timer

type Config = list[dict[str, dict[str, typing.Any]]]


def start_simulation(traci_connection, sumo_file: str, use_graph: bool = False) -> None:
    sumo_bin = get_sumo_bin(use_graph)
    try:
        traci_connection.start(
            [sumo_bin, "-c", sumo_file, "--start", "--quit-on-end"],
            stdout=subprocess.DEVNULL,
        )
    except Exception as e:
        print("Sumo start failed:", e)
        print("Terminating...")
        sys.exit(1)


SUMO_BIN_NAME = "sumo"
SUMO_BIN_NAME_GRAPH = "sumo-gui"


def get_sumo_bin(use_graph: bool) -> str:
    sumo_bin = SUMO_BIN_NAME
    if use_graph:
        sumo_bin = SUMO_BIN_NAME_GRAPH
    return sumo_bin


def disable_right_of_way_check(traci_connection) -> None:
    """
    disable_right_of_way_check sets the speed mode of all vehicle's to 55.
    For more about vehicle state, see: https://sumo.dlr.de/docs/TraCI/Change_Vehicle_State.html

    @param:
    traci_connection = active traci connection
    """
    for vehicleId in traci_connection.vehicle.getIDList():
        traci_connection.vehicle.setSpeedMode(vehicleId, 55)


def simulation_is_finished(traci_connection, timer: Optional[Timer]) -> bool:
    if timer is not None:
        return (
            traci_connection.simulation.getMinExpectedNumber() <= 0
            or timer.steps / 10 > timer.end_time
        )
    return traci_connection.simulation.getMinExpectedNumber() <= 0


def read_extender_config(filepath: str) -> Config:
    extender_config: Config = []
    with open(filepath) as conf_f:
        raw = json.load(conf_f)
        extender_config = raw["controller"].get("extender")
        if not extender_config:
            raise Exception("no extender config found in file")
    return extender_config


def write_extender_config(filepath: str, config: Config) -> None:
    existing = {}
    try:
        with open(filepath, "r") as conf_f:
            existing = json.load(conf_f)
    except FileNotFoundError:
        pass
    except json.JSONDecodeError:
        print(f"invalid JSON syntax in file {filepath}")
        existing = {"controller": {}}

    existing["controller"]["extenders"] = config

    with open(filepath, "w") as conf_f:
        json.dump(existing, conf_f, indent=4)


@dataclass
class Trip:
    type: str
    departure: float
    time_loss: float


def get_trips_from_file(filepath: str) -> list[Trip]:
    trips: list[Trip] = []
    try:
        info_tree = et.parse(filepath)
        for tripinfo in info_tree.findall("tripinfo"):
            v_type = tripinfo.get("vType")
            if v_type is None:
                v_type = "unknown"

            t_loss_str = tripinfo.get("timeLoss")
            t_loss: float = 0
            if t_loss_str is not None:
                try:
                    t_loss = float(t_loss_str)
                except ValueError:
                    print(
                        f"error converting timeLoss '{t_loss_str}' to float for tripinfo ID: {tripinfo.get('id')}"
                    )
            else:
                print(
                    f"warning: 'timeLoss' attribute missing for tripinfo ID: {tripinfo.get('id')}"
                )
                t_loss = 0

            departure_str = tripinfo.get("depart")
            departure: float = 0
            if departure_str is not None:
                try:
                    departure = float(departure_str)
                except ValueError:
                    print(
                        f"error converting depart '{departure_str}' to float for tripinfo ID: {tripinfo.get('id')}"
                    )
            else:
                print(
                    f"warning: 'depart' attribute missing for tripinfo ID: {tripinfo.get('id')}"
                )

            trip = Trip(v_type, departure, t_loss)
            trips.append(trip)

    except FileNotFoundError:
        print(f"error: File not found at {filepath}")
    except et.ParseError as e:
        print(f"error parsing XML file '{filepath}': {e}")
    return trips


def get_trips_since(traci_connection, time_seconds: float) -> list[Trip]:
    ids: list[str] = []
    for vehid in traci_connection.vehicle.getIDList():
        if traci_connection.vehicle.getDeparture(vehid) > time_seconds:
            ids.append(vehid)

    trips: list[Trip] = []
    for vehid in ids:
        v_type: str = traci_connection.vehicle.getTypeID(vehid)
        depart: float = traci_connection.vehicle.getDeparture(vehid)
        t_loss: float = traci_connection.vehicle.getTimeLoss(vehid)

        trip = Trip(v_type, depart, t_loss)
        trips.append(trip)

    return trips
