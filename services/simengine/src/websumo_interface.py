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
"""

# Copyright 2026 by Conveqs Oy and Kari Koskinen
# All Rights Reserved

import asyncio
import gzip
import json
import os
import threading
import xml.etree.ElementTree as ET

import libsumo
from nats.aio.client import Client as NATS

DEFAULT_NATS_SERVER = "localhost"
DEFAULT_NATS_PORT = 4222
CONNECT_TIMEOUT_SECONDS = 3
CLOSE_TIMEOUT_SECONDS = 3

# WebSUMO renders detector bars from these elements (both tags name the
# same SUMO e1 detector)
E1_DETECTOR_TAGS = ("e1Detector", "inductionLoop")


class WebsumoInterface:
    """Publishes the simulation state of one scenario to NATS"""

    def __init__(self, sumocfg_file, nats_conf=None, enabled=True):
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
        if not enabled:
            print("WebSUMO interface off (--nowebsumo)")
            return
        # A CRLF-mangled entrypoint script (Windows checkout) passes the
        # path with a trailing carriage return; sumo trims it, we must too
        sumocfg_file = sumocfg_file.strip()
        self.scenario = scenario_from_sumocfg(sumocfg_file)
        self._subject_prefix = "sim." + self.scenario
        self._nats_url = nats_url(nats_conf)
        self._nats = None
        # The element selected in the viewer ({"kind": ..., "id": ...})
        self._selected = None

        try:
            net_file = net_file_from_sumocfg(sumocfg_file)
            with open(net_file, "rb") as f:
                self._net_payload = gzip.compress(f.read())
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
        except Exception:
            print("Warning: no NATS server at", self._nats_url,
                  "- running without WebSUMO")
            self._stop_thread()

    async def _connect_and_serve(self):
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

    def publish_state(self):
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
                "vehicles": get_vehicle_states(),
                "persons": get_person_states(),
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

    def publish_end(self):
        """Tells the viewer that the simulation has ended"""
        if not self.connected:
            return
        self._publish(self._subject_prefix + ".end", b"{}")

    def close(self):
        """Flushes pending messages and stops the background thread"""
        if not self.connected:
            return
        self.connected = False
        try:
            asyncio.run_coroutine_threadsafe(
                self._nats.drain(), self._loop).result(
                    timeout=CLOSE_TIMEOUT_SECONDS)
        except Exception:
            pass
        self._stop_thread()

    def _publish(self, subject, payload):
        # Fire and forget: the engine never waits for the delivery
        asyncio.run_coroutine_threadsafe(
            self._nats.publish(subject, payload), self._loop)

    def _stop_thread(self):
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=CLOSE_TIMEOUT_SECONDS)


def get_vehicle_states():
    """Returns the vehicle list in the WebSUMO state format"""
    vehicles = []
    for veh_id in libsumo.vehicle.getIDList():
        pos_x, pos_y = libsumo.vehicle.getPosition(veh_id)
        lon, lat = libsumo.simulation.convertGeo(pos_x, pos_y)
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


def get_person_states():
    """Returns the pedestrian and cyclist list in the WebSUMO format"""
    persons = []
    for person_id in libsumo.person.getIDList():
        pos_x, pos_y = libsumo.person.getPosition(person_id)
        lon, lat = libsumo.simulation.convertGeo(pos_x, pos_y)
        persons.append([
            person_id,
            lon,
            lat,
            libsumo.person.getAngle(person_id),
            libsumo.person.getSpeed(person_id),
        ])
    return persons


def get_traffic_light_states():
    """Returns the signal state strings of all traffic lights"""
    lights = {}
    for tls_id in libsumo.trafficlight.getIDList():
        lights[tls_id] = libsumo.trafficlight.getRedYellowGreenState(tls_id)
    return lights


def get_detector_states():
    """Returns the occupancy status of all e1 detectors"""
    detectors = {}
    for det_id in libsumo.inductionloop.getIDList():
        vehnum = libsumo.inductionloop.getLastStepVehicleNumber(det_id)
        occup = libsumo.inductionloop.getLastStepOccupancy(det_id)
        detectors[det_id] = (vehnum > 0) or (occup > 0)
    return detectors


def get_events():
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


def get_inspect_state(selection):
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


def get_vehicle_details(veh_id):
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


def get_traffic_light_details(tls_id):
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


def scenario_from_sumocfg(sumocfg_file):
    """Returns the scenario name: the sumocfg file name without suffix"""
    return os.path.splitext(os.path.basename(sumocfg_file))[0]


def net_file_from_sumocfg(sumocfg_file):
    """Returns the path of the net file the sumocfg points at"""
    return input_files_from_sumocfg(sumocfg_file, "net-file")[0]


def merged_detectors_from_sumocfg(sumocfg_file):
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


def input_files_from_sumocfg(sumocfg_file, tag):
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


def nats_conf_from_sys_conf(sys_cnf):
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


def nats_url(nats_conf):
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
