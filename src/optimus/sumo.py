import io
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


@dataclass
class Trip:
    id: str
    type: str
    departure: float
    time_loss: float


class TripReader:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.offset = 0  # last read byte position
        self.finished = False

    def get_new_trips(self) -> dict[str, Trip]:
        trips: dict[str, Trip] = {}

        with open(self.filepath, "rb") as f:
            f.seek(self.offset)
            data = f.read()

            if not data:
                return {}

            fake_xml = b"<root>" + data + b"</root>"

            try:
                for _, elem in et.iterparse(io.BytesIO(fake_xml), events=("end",)):
                    if elem.tag != "tripinfo":
                        continue

                    veh_id = elem.get("id") or str(len(trips))
                    v_type = elem.get("vType") or "unknown"

                    def safe_float(value: str | None, default: float = 0.0) -> float:
                        if value is None:
                            return default
                        try:
                            return float(value)
                        except ValueError:
                            return default

                    t_loss = safe_float(elem.get("timeLoss"), 0.0)
                    departure = safe_float(elem.get("depart"), 0.0)

                    trips[veh_id] = Trip(veh_id, v_type, departure, t_loss)
                    elem.clear()

            except et.ParseError:
                pass

            self.offset = f.tell()

        return trips


def get_trips_from_file(filepath: str) -> dict[str, Trip]:
    trips: dict[str, Trip] = {}

    try:
        context = et.iterparse(filepath, events=("end",))
        for event, elem in context:
            if elem.tag != "tripinfo":
                continue

            veh_id = elem.get("id") or str(len(trips))
            v_type = elem.get("vType") or "unknown"

            def safe_float(value: str | None, default: float = 0.0) -> float:
                if value is None:
                    return default
                try:
                    return float(value)
                except ValueError:
                    return default

            t_loss = safe_float(elem.get("timeLoss"), 0.0)
            departure = safe_float(elem.get("depart"), 0.0)

            trip = Trip(veh_id, v_type, departure, t_loss)
            trips[veh_id] = trip

            elem.clear()

    except FileNotFoundError:
        print(f"error: File not found at {filepath}")
    except et.ParseError as e:
        print(f"warning: partial XML, parsed trips so far ({len(trips)} trips): {e}")

    return trips
