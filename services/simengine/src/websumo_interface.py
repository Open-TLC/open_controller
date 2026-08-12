""" -*- coding: utf-8 -*-
WebSUMO viewer interface for the simulation engine

Publishes the running simulation to a WebSUMO browser viewer over NATS
and serves the network file, per WebSUMO's SIM_PROTOCOL.md (version 1):

    sim.{scenario}.state   -> state frame, published from the step loop
    sim.{scenario}.net     <- request-reply: gzipped .net.xml bytes
    sim.{scenario}.cmd.*   <- viewer commands. Honoured: "select"
                              (inspection panel), "scale" (traffic
                              demand), and "pause"/"resume" (the engine
                              step loop holds in pause_gate(), and the
                              system timer is resynced on resume so the
                              simulation continues instead of
                              fast-forwarding). NOTE: the control engine
                              is wall-clock-synced and does not follow
                              the pause - signals keep cycling while the
                              simulation is held; making clockwork
                              follow is a separate TODO (see
                              doc/websumo_integration_plan.md). "speed"
                              and "stop" remain ignored.

This is a rendering surface, not an OC output: nothing in OC consumes
these subjects, and no OC behaviour depends on them (see
doc/websumo_integration_plan.md). All WebSUMO-facing code lives in this
file; the engine only constructs the interface and calls publish_state()
in its step loop.

The traci module and the NATS client are constructor arguments rather
than imports, so this module can be unit tested without SUMO or a
broker, and works with both of OC's SUMO bindings (TraCI and libsumo).
"""

# Copyright 2026 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

import asyncio
import gzip
import json
import os
import xml.etree.ElementTree

PROTOCOL_VERSION = 1


DEFAULT_STATE_RATE_HZ = 10


def defaults_from_sumo_config(sumo_config_path):
    """Viewer settings derived from the SUMO config, so no websumo conf
    block is needed for the common case: the scenario is named after the
    sumocfg and the network file is the one that sumocfg loads.

    Returns None if the network cannot be resolved (nothing to render).
    """
    config_dir = os.path.dirname(os.path.abspath(sumo_config_path))
    scenario = os.path.splitext(os.path.basename(sumo_config_path))[0]

    net_file = None
    try:
        root = xml.etree.ElementTree.parse(sumo_config_path).getroot()
        for element in root.iter("net-file"):
            value = element.get("value") or element.get("v")
            if value:
                net_file = os.path.normpath(
                    os.path.join(config_dir, value.strip()))
                break
    except (OSError, xml.etree.ElementTree.ParseError) as error:
        print("WebSUMO interface: cannot read", sumo_config_path, "-", error)
        return None

    if not net_file or not os.path.isfile(net_file):
        print("WebSUMO interface: no net-file found in", sumo_config_path)
        return None

    return {"scenario": scenario,
            "state_rate_hz": DEFAULT_STATE_RATE_HZ,
            "net_file": net_file}


def create_websumo_interface(conf, traci_mod, nats_client, step_length=0.1,
                             timer=None, sumo_config_path=None):
    """Factory for the engine call site: returns a WebsumoInterface, or
    None when the feature cannot be set up.

    `conf` is the optional "websumo" conf block; any value it omits is
    filled from the SUMO config at `sumo_config_path`, so passing no
    block at all still works. `timer` is the engine's system Timer; it
    is resynced after a pause so the simulation does not fast-forward.
    """
    if conf is None and sumo_config_path is None:
        return None

    settings = {}
    if sumo_config_path:
        settings = defaults_from_sumo_config(sumo_config_path) or {}
    settings.update(conf or {})

    if not settings.get("net_file") or not settings.get("scenario"):
        print("WebSUMO interface: not enough settings to start "
              "(need scenario and net_file); viewer disabled")
        return None

    return WebsumoInterface(settings, traci_mod, nats_client, step_length,
                            timer)


def start_for_sync_engine(conf, traci_mod, nats_url, step_length=0.1,
                          timer=None, sumo_config_path=None,
                          connect_timeout=5.0):
    """Sets the viewer up for an engine with no asyncio of its own
    (simengine_integrated.py): connects, subscribes, and returns
    (interface, event_loop). The engine drives the interface by running
    its coroutines to completion on that loop.

    Returns (None, None) if the broker is unreachable or the settings do
    not resolve - the simulation then runs exactly as it would without
    the viewer, which is why a missing NATS is a warning, not an error.
    """
    import nats

    loop = asyncio.new_event_loop()
    try:
        # Bounded: nats-py retries a missing broker for minutes, and the
        # simulation should not wait on an optional viewer
        nats_client = loop.run_until_complete(
            asyncio.wait_for(nats.connect(nats_url, max_reconnect_attempts=1),
                             timeout=connect_timeout))
    except Exception as error:  # noqa: BLE001 - viewer is optional
        print("WebSUMO interface: no NATS at {} ({}: {}); "
              "running without the viewer"
              .format(nats_url, type(error).__name__, error))
        loop.close()
        return None, None

    interface = create_websumo_interface(conf, traci_mod, nats_client,
                                         step_length, timer,
                                         sumo_config_path)
    if not interface:
        loop.run_until_complete(nats_client.close())
        loop.close()
        return None, None

    loop.run_until_complete(interface.start())
    return interface, loop


class WebsumoInterface:
    "Publishes simulation state to a WebSUMO viewer and serves the net file"

    def __init__(self, conf, traci_mod, nats_client, step_length=0.1,
                 timer=None):
        self.scenario = conf["scenario"]
        self.traci = traci_mod
        self.nats = nats_client
        self.timer = timer
        self.state_subject = "sim." + self.scenario + ".state"
        self.net_subject = "sim." + self.scenario + ".net"
        self.cmd_subject = "sim." + self.scenario + ".cmd.*"
        self.selected = None
        self.paused = False

        # The net is read and compressed once, at construction, so a bad
        # path fails at startup rather than on the viewer's first request
        with open(conf["net_file"], "rb") as net_file:
            self.net_gzipped = gzip.compress(net_file.read())

        # Publish every Nth step so the wire rate matches state_rate_hz
        rate_hz = conf.get("state_rate_hz", DEFAULT_STATE_RATE_HZ)
        steps_per_second = 1.0 / step_length
        self.publish_every = max(1, round(steps_per_second / rate_hz))
        self.step_count = 0

    async def start(self):
        """Subscribes the net request-reply and the command subjects;
        call once, after the NATS client is connected"""
        async def reply_with_net(msg):
            await msg.respond(self.net_gzipped)
        await self.nats.subscribe(self.net_subject, cb=reply_with_net)
        await self.nats.subscribe(self.cmd_subject, cb=self.handle_command)
        print("WebSUMO interface: serving", self.net_subject,
              "and publishing", self.state_subject)

    async def handle_command(self, msg):
        """Applies a viewer command; unknown or malformed commands are
        silently ignored, per the protocol"""
        command = msg.subject.rsplit(".", 1)[-1]
        try:
            data = json.loads(msg.data.decode()) if msg.data else {}
        except (ValueError, UnicodeDecodeError):
            return

        if command == "pause":
            self.paused = True

        elif command == "resume":
            self.paused = False

        elif command == "scale":
            # Traffic demand multiplier; time-neutral, so safe to honour
            value = data.get("v")
            if isinstance(value, (int, float)):
                self.traci.simulation.setScale(min(max(value, 0.0), 5.0))

        elif command == "select":
            # Single global selection for the inspection panel
            kind = data.get("kind")
            element_id = data.get("id")
            if kind in ("vehicle", "tls") and element_id:
                self.selected = {"kind": kind, "id": element_id}
                # One-shot so the panel fills without waiting for the
                # next frame (mirrors WebSUMO's own adapter behaviour)
                one_shot = {"type": "inspect",
                            "inspect": self.build_inspect_block()}
                await self.nats.publish(self.state_subject,
                                        json.dumps(one_shot).encode())
            else:
                self.selected = None

    def build_inspect_block(self):
        """Details of the selected element, or a 'gone' marker if it has
        left the simulation (field set mirrors WebSUMO's adapter)"""
        try:
            if self.selected["kind"] == "vehicle":
                return self.inspect_vehicle(self.selected["id"])
            return self.inspect_tls(self.selected["id"])
        except Exception:
            return {"kind": self.selected["kind"],
                    "id": self.selected["id"], "gone": True}

    def inspect_vehicle(self, veh_id):
        "Live and static properties of one vehicle"
        vehicle = self.traci.vehicle
        leader = vehicle.getLeader(veh_id)
        next_tls = vehicle.getNextTLS(veh_id)
        return {
            "kind": "vehicle", "id": veh_id,
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
            "accumWaiting":
                round(vehicle.getAccumulatedWaitingTime(veh_id), 1),
            "timeLoss": round(vehicle.getTimeLoss(veh_id), 1),
            "distance": round(vehicle.getDistance(veh_id), 1),
            "leader":
                [leader[0], round(leader[1], 1)] if leader else None,
            "nextTLS":
                [next_tls[0][0], round(next_tls[0][2], 1), next_tls[0][3]]
                if next_tls else None,
            "speedFactor": round(vehicle.getSpeedFactor(veh_id), 3),
            "length": vehicle.getLength(veh_id),
            "width": vehicle.getWidth(veh_id),
            "minGap": vehicle.getMinGap(veh_id),
        }

    def inspect_tls(self, tls_id):
        "Live and static properties of one traffic light"
        trafficlight = self.traci.trafficlight
        program = trafficlight.getProgram(tls_id)
        phases = []
        for logic in trafficlight.getAllProgramLogics(tls_id):
            if logic.programID == program:
                phases = [[p.duration, p.state] for p in logic.phases]
                break
        next_switch = trafficlight.getNextSwitch(tls_id)
        # getSpentDuration only exists in newer SUMO (not 1.18, which the
        # simengine image ships); derive it from what 1.18 does provide
        spent = (trafficlight.getPhaseDuration(tls_id)
                 - (next_switch - self.traci.simulation.getTime()))
        return {
            "kind": "tls", "id": tls_id,
            "program": program,
            "phase": trafficlight.getPhase(tls_id),
            "state": trafficlight.getRedYellowGreenState(tls_id),
            "nextSwitch": round(next_switch, 1),
            "spent": round(spent, 1),
            "phases": phases,
        }

    def build_state_frame(self):
        """Reads the current simulation state into a protocol v1 frame"""
        traci = self.traci
        vehicles = []
        for veh_id in traci.vehicle.getIDList():
            pos_x, pos_y = traci.vehicle.getPosition(veh_id)
            lon, lat = traci.simulation.convertGeo(pos_x, pos_y)
            vehicles.append([
                veh_id,
                round(lon, 7),
                round(lat, 7),
                round(traci.vehicle.getAngle(veh_id), 1),
                round(traci.vehicle.getLength(veh_id), 2),
                round(traci.vehicle.getWidth(veh_id), 2),
                traci.vehicle.getVehicleClass(veh_id),
            ])

        tls = {}
        for tls_id in traci.trafficlight.getIDList():
            tls[tls_id] = traci.trafficlight.getRedYellowGreenState(tls_id)

        detectors = {}
        for det_id in traci.inductionloop.getIDList():
            detectors[det_id] = (
                traci.inductionloop.getLastStepVehicleNumber(det_id) > 0
                or traci.inductionloop.getLastStepOccupancy(det_id) > 0)

        frame = {
            "v": PROTOCOL_VERSION,
            "t": round(traci.simulation.getTime(), 1),
            "vehicles": vehicles,
            "persons": [],  # pedestrians not tracked in phase 1
            "tls": tls,
            "detectors": detectors,
        }
        if self.selected:
            frame["inspect"] = self.build_inspect_block()
        return frame

    async def pause_gate(self):
        """Holds while the viewer has paused the simulation; call in the
        step loop before advancing SUMO. Returns immediately when not
        paused. On resume the system timer's drift integrator is reset
        (Timer.reset_time_step, the hook made for exactly this) so the
        simulation continues in real time instead of fast-forwarding to
        catch up the paused wall-clock time."""
        if not self.paused:
            return
        print("WebSUMO interface: simulation paused by viewer")
        while self.paused:
            await asyncio.sleep(0.05)
        if self.timer:
            self.timer.reset_time_step()
        print("WebSUMO interface: simulation resumed")

    async def publish_state(self):
        """Publishes a state frame; call every simulation step, the
        decimation to state_rate_hz happens here"""
        self.step_count += 1
        if self.step_count % self.publish_every != 0:
            return
        frame = self.build_state_frame()
        await self.nats.publish(self.state_subject,
                                json.dumps(frame).encode())
