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
import threading
import time

PROTOCOL_VERSION = 1


def create_websumo_interface(conf, traci_mod, nats_client, step_length=0.1,
                             timer=None):
    """Factory for the engine call site: returns a WebsumoInterface, or
    None when conf is None (the feature is off unless the simengine conf
    has a "websumo" block). `timer` is the engine's system Timer; it is
    resynced after a pause so the simulation does not fast-forward."""
    if not conf:
        return None
    return WebsumoInterface(conf, traci_mod, nats_client, step_length, timer)


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
        # Commands arrive on the NATS thread but touch SUMO, so they are
        # parked here and applied by the thread that steps the simulation
        self.pending_scale = None
        self.inspect_pending = False
        self.inspect_error_reported = False

        # The net is read and compressed once, at construction, so a bad
        # path fails at startup rather than on the viewer's first request
        with open(conf["net_file"], "rb") as net_file:
            self.net_gzipped = gzip.compress(net_file.read())

        # Publish every Nth step so the wire rate matches state_rate_hz
        rate_hz = conf.get("state_rate_hz", 10)
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
                self.pending_scale = min(max(value, 0.0), 5.0)

        elif command == "select":
            # Single global selection for the inspection panel
            kind = data.get("kind")
            element_id = data.get("id")
            if kind in ("vehicle", "tls") and element_id:
                self.selected = {"kind": kind, "id": element_id}
                self.inspect_error_reported = False
                # One-shot so the panel fills without waiting for the
                # next frame (mirrors WebSUMO's own adapter behaviour),
                # and so selecting while paused works at all
                self.inspect_pending = True
            else:
                self.selected = None
                self.inspect_pending = False

    def take_pending_scale(self):
        """Returns a pending scale value once, or None. Applying it (a
        traci call) is the caller's job so it happens on the thread that
        steps SUMO - libsumo is not thread safe"""
        value, self.pending_scale = self.pending_scale, None
        return value

    def take_pending_inspect(self):
        """Returns the one-shot inspect message once, or None. Built by
        the caller's thread for the same reason as take_pending_scale"""
        if not self.inspect_pending or not self.selected:
            return None
        self.inspect_pending = False
        return {"type": "inspect", "inspect": self.build_inspect_block()}

    async def apply_pending_commands(self):
        """Applies commands collected since the last step and publishes
        any one-shot inspect; call from the step loop before advancing
        SUMO (the order SIM_PROTOCOL.md prescribes)"""
        scale = self.take_pending_scale()
        if scale is not None:
            self.traci.simulation.setScale(scale)
        one_shot = self.take_pending_inspect()
        if one_shot:
            await self.nats.publish(self.state_subject,
                                    json.dumps(one_shot).encode())

    def build_inspect_block(self):
        """Details of the selected element, or a 'gone' marker if it has
        left the simulation (field set mirrors WebSUMO's adapter)"""
        try:
            if self.selected["kind"] == "vehicle":
                return self.inspect_vehicle(self.selected["id"])
            return self.inspect_tls(self.selected["id"])
        except Exception as error:
            # Usually the element simply left the simulation, which is a
            # normal 'gone' answer - but the same catch would hide a real
            # API mismatch, so report the first one per selection
            if not self.inspect_error_reported:
                self.inspect_error_reported = True
                print("WebSUMO interface: inspect of {} {} failed: {}: {}"
                      .format(self.selected["kind"], self.selected["id"],
                              type(error).__name__, error))
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
            # Keep serving selections while held, or the inspection
            # panel would stay empty for anything clicked during a pause
            await self.apply_pending_commands()
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


def create_sync_websumo_interface(conf, traci_mod, nats_url,
                                  step_length=0.1, timer=None):
    """Factory for a synchronous engine (simengine_integrated.py):
    returns a SyncWebsumoInterface, or None when conf is None"""
    if not conf:
        return None
    return SyncWebsumoInterface(conf, traci_mod, nats_url, step_length,
                                timer)


class SyncWebsumoInterface:
    """The same interface for an engine with no asyncio of its own.

    NATS is asyncio-only, so it runs in a background thread; the engine
    calls the plain methods below from its step loop. Everything that
    touches SUMO happens on the calling (stepping) thread - the
    background thread only moves bytes - because libsumo is not thread
    safe.
    """

    def __init__(self, conf, traci_mod, nats_url, step_length=0.1,
                 timer=None, connect_timeout=10.0):
        self.nats_url = nats_url
        self.interface = None
        self._loop = None
        self._ready = threading.Event()
        self._error = None
        self._conf = conf
        self._traci = traci_mod
        self._step_length = step_length
        self._timer = timer

        self._thread = threading.Thread(target=self._run_loop, daemon=True,
                                        name="websumo-nats")
        self._thread.start()
        # Fail loudly rather than handing back a half-built interface:
        # a broker that is down makes nats-py retry with backoff, which
        # would otherwise look like a silent timeout here
        connected = self._ready.wait(timeout=connect_timeout)
        if self._error:
            raise self._error
        if not connected or not self.interface:
            raise RuntimeError(
                "WebSUMO interface: could not connect to NATS at {} within "
                "{} s".format(self.nats_url, connect_timeout))

    def _run_loop(self):
        "Owns the event loop and the NATS connection"
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._connect())
            self._loop.run_forever()
        except Exception as error:  # noqa: BLE001 - reported to caller
            self._error = error
            self._ready.set()

    async def _connect(self):
        # Imported here, not at module level, so the unit tests can
        # exercise this module without nats-py installed
        import nats

        nats_client = await nats.connect(self.nats_url)
        self.interface = WebsumoInterface(self._conf, self._traci,
                                          nats_client, self._step_length,
                                          self._timer)
        await self.interface.start()
        self._ready.set()

    def _publish(self, payload):
        "Hands a built message to the background loop to send"
        asyncio.run_coroutine_threadsafe(
            self.interface.nats.publish(self.interface.state_subject,
                                        json.dumps(payload).encode()),
            self._loop)

    def apply_pending_commands(self):
        "Applies collected commands; call before stepping SUMO"
        scale = self.interface.take_pending_scale()
        if scale is not None:
            self._traci.simulation.setScale(scale)
        one_shot = self.interface.take_pending_inspect()
        if one_shot:
            self._publish(one_shot)

    def pause_gate(self):
        """Blocks while the viewer has paused; call before stepping SUMO.

        Returns the number of wall-clock seconds spent paused (0.0 when
        not paused). The integrated engine paces itself against its own
        `next_update_time` accumulator, so it must add this to it -
        otherwise it steps flat out after a resume until the accumulator
        catches up with wall time.
        """
        if not self.interface.paused:
            return 0.0
        print("WebSUMO interface: simulation paused by viewer")
        paused_at = time.time()
        while self.interface.paused:
            self.apply_pending_commands()
            time.sleep(0.05)
        paused_for = time.time() - paused_at
        if self._timer:
            self._timer.reset_time_step()
        print("WebSUMO interface: simulation resumed after {:.1f} s"
              .format(paused_for))
        return paused_for

    def publish_state(self):
        "Publishes a state frame; call every simulation step"
        self.interface.step_count += 1
        if self.interface.step_count % self.interface.publish_every != 0:
            return
        self._publish(self.interface.build_state_frame())

    def close(self):
        "Stops the background loop; safe to call more than once"
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=2.0)
