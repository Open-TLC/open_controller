""" -*- coding: utf-8 -*-
WebSUMO viewer interface for the simulation engine

Publishes the running simulation to a WebSUMO browser viewer over NATS
and serves the network file, per WebSUMO's SIM_PROTOCOL.md (version 1):

    sim.{scenario}.state   -> state frame, published from the step loop
    sim.{scenario}.net     <- request-reply: gzipped .net.xml bytes

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

import gzip
import json

PROTOCOL_VERSION = 1


def create_websumo_interface(conf, traci_mod, nats_client, step_length=0.1):
    """Factory for the engine call site: returns a WebsumoInterface, or
    None when conf is None (the feature is off unless the simengine conf
    has a "websumo" block)"""
    if not conf:
        return None
    return WebsumoInterface(conf, traci_mod, nats_client, step_length)


class WebsumoInterface:
    "Publishes simulation state to a WebSUMO viewer and serves the net file"

    def __init__(self, conf, traci_mod, nats_client, step_length=0.1):
        self.scenario = conf["scenario"]
        self.traci = traci_mod
        self.nats = nats_client
        self.state_subject = "sim." + self.scenario + ".state"
        self.net_subject = "sim." + self.scenario + ".net"

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
        """Subscribes the net request-reply; call once, after the NATS
        client is connected"""
        async def reply_with_net(msg):
            await msg.respond(self.net_gzipped)
        await self.nats.subscribe(self.net_subject, cb=reply_with_net)
        print("WebSUMO interface: serving", self.net_subject,
              "and publishing", self.state_subject)

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

        return {
            "v": PROTOCOL_VERSION,
            "t": round(traci.simulation.getTime(), 1),
            "vehicles": vehicles,
            "persons": [],  # pedestrians not tracked in phase 1
            "tls": tls,
            "detectors": detectors,
        }

    async def publish_state(self):
        """Publishes a state frame; call every simulation step, the
        decimation to state_rate_hz happens here"""
        self.step_count += 1
        if self.step_count % self.publish_every != 0:
            return
        frame = self.build_state_frame()
        await self.nats.publish(self.state_subject,
                                json.dumps(frame).encode())
