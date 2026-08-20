# -*- coding: utf-8 -*-
"""The WebSUMO viewer interface

This module publishes the simulation state to a NATS server so that a
running simulation can be viewed with the WebSUMO viewer. The subjects
and the payloads are defined by WebSUMO (docs/SIM_PROTOCOL.md, v 1.0):

    sim.{scenario}.state      published after every simulation step
    sim.{scenario}.log        published when there are events (collisions)
    sim.{scenario}.end        published once when the simulation ends
    sim.{scenario}.net        request-reply, the gzipped net file
    sim.{scenario}.detectors  request-reply, gzipped merged e1 detectors
    sim.{scenario}.cmd.select subscribed: details of the selected element
                              are included in the state ("inspect")

The scenario name and the served files are derived from the sumocfg the
engine is already running. The interface is for viewing only: of the
sim.{scenario}.cmd.* subjects only "select" is subscribed, and its only
effect is reading more data for the viewer. The run control commands
(pause, resume, stop, speed, scale, spawn) are ignored, and there is no
timing logic of any kind. The engine's timer owns the update cadence
and this module publishes whatever the engine's own tick produces.

If the NATS server cannot be reached, a warning is printed and every
operation becomes a no-op: the simulation runs exactly as it would
without the viewer.

All NATS I/O runs in a background thread with its own asyncio event
loop, so the same module works from the synchronous integrated engine
and from the asynchronous independent engine. The thread only relays
the messages, it never touches the simulation.

The thread exists only because of simengine_integrated.py: it is a
plain synchronous loop with no event loop of its own, and nats-py is
asyncio-only, so a background loop is the only way to call it at all.
simengine.py already runs its own asyncio loop and already holds a
connected NATS client, so for that engine this thread is a second,
redundant connection to the same broker - accepted here in exchange for
one implementation shared by both engines instead of two. If
simengine_integrated.py is ever rewritten around asyncio, this thread
can go and both engines can call NATS directly on their own loop.
"""

# Copyright 2026 by Conveqs Oy and Kari Koskinen
# All Rights Reserved

from __future__ import annotations

import asyncio
import gzip
import io
import json
import math
import os
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import Future
from typing import Any, Callable

import libsumo
from nats.aio.client import Client as NATS

DEFAULT_NATS_SERVER = "localhost"
DEFAULT_NATS_PORT = 4222
CONNECT_TIMEOUT_SECONDS = 3
CLOSE_TIMEOUT_SECONDS = 3

# WebSUMO renders detector bars from these elements (both tags name the
# same SUMO e1 detector)
E1_DETECTOR_TAGS = ("e1Detector", "inductionLoop")

# Nets without a geo-reference (projParameter="!" in the <location>
# element) still get a working viewer: the net is anchored at lon/lat
# 0,0 using spherical web mercator - the projection MapLibre renders
# in, so near 0,0 the shapes stay meter-true and undistorted. The
# served net file gets this projection injected into its header, so
# WebSUMO's own sumolib conversion of the network geometry agrees
# exactly with the positions published from here. 0,0 is open ocean:
# the viewer works normally, there is just no map background to toggle
# on. (Revisit when WebSUMO gets a native no-geo mode.)
NO_PROJECTION = b'projParameter="!"'
SYNTHETIC_PROJ = ("+proj=merc +a=6378137 +b=6378137 +lat_ts=0 +lon_0=0 "
                  "+x_0=0 +y_0=0 +k=1 +units=m +no_defs")
SYNTHETIC_PROJECTION = ('projParameter="' + SYNTHETIC_PROJ + '"').encode()
EARTH_RADIUS_M = 6378137.0

# An x/y meters to lon/lat degrees conversion function
GeoConverter = Callable[[float, float], "tuple[float, float]"]


class WebsumoInterface:
    """Publishes the simulation state of one scenario to NATS"""

    def __init__(self, sumocfg_file: str, nats_conf: dict | str | None = None,
                 enabled: bool = True) -> None:
        """Connects to NATS and starts serving the scenario files

        sumocfg_file: path of the sumocfg the engine is running, used
            for deriving the scenario name and the served files
        nats_conf: the NATS server address, either a dictionary with
            "server" (or "ip") and "port" keys as used in the conf
            files, or an "ip:port" string as returned by
            GlobalConf.get_nats_params(). Defaults to localhost:4222.
        enabled: False (the --nowebsumo param) makes every operation
            a no-op without touching NATS at all
        """
        self.connected = False
        self._thread = None
        if not enabled:
            print("WebSUMO interface off (--nowebsumo)")
            return
        # A CRLF-mangled entrypoint script (Windows checkout) passes the
        # path with a trailing carriage return; sumo trims it, we must too
        sumocfg_file = sumocfg_file.strip()
        self.scenario = scenario_from_sumocfg(sumocfg_file)
        # The scenario name becomes part of the NATS subjects, which must
        # not contain spaces or wildcard characters
        if any(char in self.scenario for char in " \t*>"):
            print("Warning: running without WebSUMO - the sumocfg name",
                  repr(self.scenario), "is not a valid NATS subject token")
            return
        self._subject_prefix = "sim." + self.scenario
        self._nats_url = nats_url(nats_conf)
        self._nats = None
        # The element selected in the viewer ({"kind": ..., "id": ...})
        self._selected = None

        try:
            net_file = net_file_from_sumocfg(sumocfg_file)
            with open(net_file, "rb") as f:
                net_bytes = f.read()
            net_bytes, self._geo_offset = _geo_reference_net(net_bytes)
            if self._geo_offset is None:
                self._convert_geo = libsumo.simulation.convertGeo
            else:
                print("WebSUMO: the net has no geo-projection, "
                      "anchoring the view at lon/lat 0,0")
                self._convert_geo = self._synthetic_convert
            self._net_payload = gzip.compress(net_bytes)
            detectors = merged_detectors_from_sumocfg(sumocfg_file)
            if detectors is None:
                self._detectors_payload = None
            else:
                self._detectors_payload = gzip.compress(detectors)
        except (OSError, ET.ParseError, IndexError) as e:
            print("Warning: WebSUMO interface disabled, "
                  "cannot read the scenario files:", e)
            return

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="websumo-nats", daemon=True)
        self._thread.start()
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._connect_and_serve(), self._loop)
            future.result(timeout=CONNECT_TIMEOUT_SECONDS)
            self.connected = True
            print("WebSUMO interface publishing scenario",
                  self.scenario, "to", self._nats_url)
        except Exception as e:
            print("Warning: running without WebSUMO - could not connect to",
                  self._nats_url, ":", e)
            self._stop_thread()

    async def _connect_and_serve(self) -> None:
        """Connects to the nats server and answers the file requests"""
        self._nats = NATS()
        await self._nats.connect(
            self._nats_url, connect_timeout=CONNECT_TIMEOUT_SECONDS - 1)

        async def reply_net(msg):
            await msg.respond(self._net_payload)

        async def reply_detectors(msg):
            await msg.respond(self._detectors_payload)

        async def on_select(msg):
            try:
                selection = json.loads(msg.data) if msg.data else {}
            except json.JSONDecodeError:
                selection = {}
            if "kind" in selection and "id" in selection:
                self._selected = selection
            else:
                self._selected = None

        await self._nats.subscribe(self._subject_prefix + ".net",
                                   cb=reply_net)
        if self._detectors_payload is not None:
            await self._nats.subscribe(self._subject_prefix + ".detectors",
                                       cb=reply_detectors)
        await self._nats.subscribe(self._subject_prefix + ".cmd.select",
                                   cb=on_select)

    def publish_state(self) -> None:
        """Reads the current state from sumo and publishes it

        Called from the engine's own update tick, right after
        simulationStep(). No-op when there is no NATS connection.
        """
        if not self.connected:
            return
        # The engine must never be interrupted by the viewer: any
        # failure here disables the interface instead of raising
        try:
            state = {
                "v": 1,
                "t": round(libsumo.simulation.getTime(), 1),
                "vehicles": get_vehicle_states(self._convert_geo),
                "persons": get_person_states(self._convert_geo),
                "tls": get_traffic_light_states(),
                "detectors": get_detector_states(),
                "_empty": libsumo.simulation.getMinExpectedNumber() == 0,
            }
            events = get_events()
            if events:
                state["events"] = events
            selection = self._selected
            if selection is not None:
                state["inspect"] = get_inspect_state(selection)
        except Exception as e:
            print("Warning: WebSUMO interface disabled, "
                  "reading the simulation state failed:", e)
            self.connected = False
            self._stop_thread()
            return
        self._publish(self._subject_prefix + ".state",
                      json.dumps(state).encode())
        if events:
            log_message = {"type": "log", "t": state["t"], "events": events}
            self._publish(self._subject_prefix + ".log",
                          json.dumps(log_message).encode())

    def publish_end(self) -> None:
        """Tells the viewer that the simulation has ended"""
        if not self.connected:
            return
        self._publish(self._subject_prefix + ".end", b"{}")

    def close(self) -> None:
        """Flushes pending messages and stops the background thread"""
        if self.connected:
            self.connected = False
            try:
                asyncio.run_coroutine_threadsafe(
                    self._nats.drain(), self._loop).result(
                        timeout=CLOSE_TIMEOUT_SECONDS)
            except Exception:
                pass
        if self._thread is not None:
            self._stop_thread()

    def _publish(self, subject: str, payload: bytes) -> None:
        # Fire and forget: the engine never waits for the delivery, but
        # a failed delivery (broker gone mid-run) disables the interface
        future = asyncio.run_coroutine_threadsafe(
            self._nats.publish(subject, payload), self._loop)
        future.add_done_callback(self._check_publish_result)

    def _check_publish_result(self, future: Future) -> None:
        """Disables the interface when a publish fails (broker gone)"""
        try:
            error = future.exception()
        except (Exception, asyncio.CancelledError):
            return
        if error is not None and self.connected:
            print("Warning: WebSUMO interface disabled, "
                  "publishing failed:", error)
            self.connected = False

    def _stop_thread(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=CLOSE_TIMEOUT_SECONDS)

    def _synthetic_convert(self, x: float, y: float) -> tuple[float, float]:
        """convertGeo() replacement for a net without a geo-projection

        libsumo's convertGeo() does not fail on such a net - it silently
        returns the x/y meters unchanged, which the viewer would read as
        degrees. This converts with the synthetic projection instead.
        """
        return _synthetic_lonlat(x, y, self._geo_offset)


def get_vehicle_states(convert_geo: GeoConverter) -> list[list]:
    """Returns the vehicle list in the WebSUMO state format

    convert_geo: the x/y meters to lon/lat conversion, normally
        libsumo.simulation.convertGeo (synthetic for a no-geo net)
    """
    vehicles = []
    for veh_id in libsumo.vehicle.getIDList():
        pos_x, pos_y = libsumo.vehicle.getPosition(veh_id)
        lon, lat = convert_geo(pos_x, pos_y)
        vehicles.append([
            veh_id,
            lon,
            lat,
            libsumo.vehicle.getAngle(veh_id),
            libsumo.vehicle.getLength(veh_id),
            libsumo.vehicle.getWidth(veh_id),
            libsumo.vehicle.getVehicleClass(veh_id),
        ])
    return vehicles


def get_person_states(convert_geo: GeoConverter) -> list[list]:
    """Returns the pedestrian and cyclist list in the WebSUMO format

    convert_geo: as in get_vehicle_states()
    """
    persons = []
    for person_id in libsumo.person.getIDList():
        pos_x, pos_y = libsumo.person.getPosition(person_id)
        lon, lat = convert_geo(pos_x, pos_y)
        persons.append([
            person_id,
            lon,
            lat,
            libsumo.person.getAngle(person_id),
            libsumo.person.getSpeed(person_id),
        ])
    return persons


def get_traffic_light_states() -> dict[str, str]:
    """Returns the signal state strings of all traffic lights"""
    lights = {}
    for tls_id in libsumo.trafficlight.getIDList():
        lights[tls_id] = libsumo.trafficlight.getRedYellowGreenState(tls_id)
    return lights


def get_detector_states() -> dict[str, bool]:
    """Returns the occupancy status of all e1 detectors"""
    detectors = {}
    for det_id in libsumo.inductionloop.getIDList():
        vehnum = libsumo.inductionloop.getLastStepVehicleNumber(det_id)
        occup = libsumo.inductionloop.getLastStepOccupancy(det_id)
        detectors[det_id] = (vehnum > 0) or (occup > 0)
    return detectors


def get_events() -> list[dict]:
    """Returns the exceptional events of this step

    Collisions, teleports and emergency stops, as shown in the
    viewer's log panel. Empty list on a normal step.
    """
    events = []
    for collision in libsumo.simulation.getCollisions():
        events.append({
            "type": "collision",
            "text": collision.collider + " vs " + collision.victim,
            "lane": collision.lane,
        })
    for veh_id in libsumo.simulation.getStartingTeleportIDList():
        events.append({"type": "teleport", "text": veh_id})
    for veh_id in libsumo.simulation.getEmergencyStoppingVehiclesIDList():
        events.append({"type": "emergency", "text": veh_id})
    return events


def get_inspect_state(selection: dict) -> dict:
    """Returns the details of the element selected in the viewer

    The field names follow the WebSUMO protocol. A "gone" marker is
    returned if the selected element is no longer in the simulation.
    """
    try:
        if selection["kind"] == "vehicle":
            return get_vehicle_details(selection["id"])
        if selection["kind"] == "tls":
            return get_traffic_light_details(selection["id"])
    except Exception:
        pass
    return {"kind": selection.get("kind"),
            "id": selection.get("id"),
            "gone": True}


def get_vehicle_details(veh_id: str) -> dict[str, Any]:
    """Returns the inspection details of one vehicle"""
    vehicle = libsumo.vehicle
    leader = vehicle.getLeader(veh_id)
    next_tls = vehicle.getNextTLS(veh_id)
    return {
        "kind": "vehicle",
        "id": veh_id,
        "type": vehicle.getTypeID(veh_id),
        "vclass": vehicle.getVehicleClass(veh_id),
        "speed": round(vehicle.getSpeed(veh_id), 2),
        "allowedSpeed": round(vehicle.getAllowedSpeed(veh_id), 2),
        "accel": round(vehicle.getAcceleration(veh_id), 2),
        "lane": vehicle.getLaneID(veh_id),
        "lanePos": round(vehicle.getLanePosition(veh_id), 1),
        "route": vehicle.getRouteID(veh_id),
        "routeEdges": list(vehicle.getRoute(veh_id)),
        "routeIndex": vehicle.getRouteIndex(veh_id),
        "departure": round(vehicle.getDeparture(veh_id), 1),
        "departDelay": round(vehicle.getDepartDelay(veh_id), 1),
        "waiting": round(vehicle.getWaitingTime(veh_id), 1),
        "accumWaiting": round(vehicle.getAccumulatedWaitingTime(veh_id), 1),
        "timeLoss": round(vehicle.getTimeLoss(veh_id), 1),
        "distance": round(vehicle.getDistance(veh_id), 1),
        "leader": [leader[0], round(leader[1], 1)] if leader else None,
        "nextTLS": ([next_tls[0][0], round(next_tls[0][2], 1), next_tls[0][3]]
                    if next_tls else None),
        "speedFactor": round(vehicle.getSpeedFactor(veh_id), 3),
        "length": vehicle.getLength(veh_id),
        "width": vehicle.getWidth(veh_id),
        "minGap": vehicle.getMinGap(veh_id),
    }


def get_traffic_light_details(tls_id: str) -> dict[str, Any]:
    """Returns the inspection details of one traffic light"""
    trafficlight = libsumo.trafficlight
    program = trafficlight.getProgram(tls_id)
    phases = []
    for logic in trafficlight.getAllProgramLogics(tls_id):
        if logic.programID == program:
            phases = [[phase.duration, phase.state] for phase in logic.phases]
            break
    return {
        "kind": "tls",
        "id": tls_id,
        "program": program,
        "phase": trafficlight.getPhase(tls_id),
        "state": trafficlight.getRedYellowGreenState(tls_id),
        "nextSwitch": round(trafficlight.getNextSwitch(tls_id), 1),
        "spent": round(trafficlight.getSpentDuration(tls_id), 1),
        "phases": phases,
    }


def _geo_reference_net(
        net_bytes: bytes) -> tuple[bytes, tuple[float, float] | None]:
    """Injects the synthetic projection if the net has none

    Returns (net_bytes, net_offset): the net file bytes to serve and,
    when the synthetic projection was injected, the netOffset needed by
    _synthetic_lonlat(). net_offset is None for a net that already has a
    real geo-projection (the bytes are returned unchanged).
    """
    if NO_PROJECTION not in net_bytes:
        return net_bytes, None
    return (net_bytes.replace(NO_PROJECTION, SYNTHETIC_PROJECTION, 1),
            _net_offset_from_net(net_bytes))


def _net_offset_from_net(net_bytes: bytes) -> tuple[float, float]:
    """Returns the netOffset pair of the net file's <location> element"""
    for _, element in ET.iterparse(io.BytesIO(net_bytes)):
        if element.tag == "location":
            x_offset, _, y_offset = element.get(
                "netOffset", "0.00,0.00").partition(",")
            return float(x_offset), float(y_offset)
    return 0.0, 0.0


def _synthetic_lonlat(x: float, y: float,
                      net_offset: tuple[float, float] = (0.0, 0.0),
                      ) -> tuple[float, float]:
    """Converts net x/y meters to lon/lat in the synthetic projection

    The exact inverse of SYNTHETIC_PROJ (spherical web mercator), with
    the netOffset removed first - the same conversion sumolib's
    convertXY2LonLat() performs on the served net file, so the
    published positions and the viewer's network geometry agree.
    """
    x -= net_offset[0]
    y -= net_offset[1]
    lon = math.degrees(x / EARTH_RADIUS_M)
    lat = math.degrees(2.0 * math.atan(math.exp(y / EARTH_RADIUS_M))
                       - math.pi / 2.0)
    return lon, lat


def scenario_from_sumocfg(sumocfg_file: str) -> str:
    """Returns the scenario name: the sumocfg file name without suffix"""
    return os.path.splitext(os.path.basename(sumocfg_file))[0]


def net_file_from_sumocfg(sumocfg_file: str) -> str:
    """Returns the path of the net file the sumocfg points at"""
    return input_files_from_sumocfg(sumocfg_file, "net-file")[0]


def merged_detectors_from_sumocfg(sumocfg_file: str) -> bytes | None:
    """Returns all e1 detectors of the scenario as one xml document

    WebSUMO renders the detector bars from a single detector file, but
    the models here split the detectors over several additional files.
    This collects the e1 detector elements of all additional files
    under one root. Returns None if there are no e1 detectors.
    """
    merged = ET.Element("additional")
    for file_name in input_files_from_sumocfg(sumocfg_file,
                                              "additional-files"):
        try:
            root = ET.parse(file_name).getroot()
        except (OSError, ET.ParseError):
            print("Warning: could not read additional file:", file_name)
            continue
        for tag in E1_DETECTOR_TAGS:
            for detector in root.iter(tag):
                merged.append(detector)
    if len(merged) == 0:
        return None
    return ET.tostring(merged)


def input_files_from_sumocfg(sumocfg_file: str, tag: str) -> list[str]:
    """Returns the paths listed in one input tag of the sumocfg

    The paths in the sumocfg are relative to the sumocfg itself; the
    returned paths are joined with its directory. The models use both
    the "value" and the abbreviated "v" attribute.
    """
    root = ET.parse(sumocfg_file).getroot()
    element = root.find("input/" + tag)
    if element is None:
        return []
    value = element.get("value") or element.get("v") or ""
    base_dir = os.path.dirname(sumocfg_file)
    return [os.path.join(base_dir, name.strip())
            for name in value.split(",") if name.strip()]


def nats_conf_from_sys_conf(sys_cnf: dict) -> dict:
    """Returns the nats parameters for the interface from the conf

    The conf file's "nats" section, overridden by the --nats-server and
    --nats-port command line params (which the integrated conf reader
    merges into the "sumo" section).
    """
    nats_conf = dict(sys_cnf.get("nats") or {})
    sumo_params = sys_cnf.get("sumo") or {}
    if sumo_params.get("nats_server"):
        nats_conf["server"] = sumo_params["nats_server"]
    if sumo_params.get("nats_port"):
        nats_conf["port"] = sumo_params["nats_port"]
    return nats_conf


def nats_url(nats_conf: dict | str | None) -> str:
    """Returns the nats server url for the given conf value

    Accepts the conf dictionary format ({"server": ..., "port": ...},
    "ip" also accepted), an "ip:port" string, or None for the default
    localhost:4222.
    """
    server = DEFAULT_NATS_SERVER
    port = DEFAULT_NATS_PORT
    if isinstance(nats_conf, str) and nats_conf:
        server, _, conf_port = nats_conf.partition(":")
        if conf_port:
            port = conf_port
    elif isinstance(nats_conf, dict):
        server = nats_conf.get("server", nats_conf.get("ip", server))
        port = nats_conf.get("port", port)
    return "nats://" + str(server) + ":" + str(port)
