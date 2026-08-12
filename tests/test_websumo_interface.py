"""Unit tests for the WebSUMO viewer interface.

The traci module and the NATS client are constructor arguments of the
interface, so these tests run without SUMO or a broker: FakeTraci serves
canned simulation state, FakeNats records what would go on the wire.
The frame assertions follow WebSUMO's SIM_PROTOCOL.md (version 1).
"""

import asyncio
import gzip
import json
import os
import tempfile
import unittest

from services.simengine.src.websumo_interface import (
    create_websumo_interface,
)


class FakeVehicle:
    def __init__(self, vehicles):
        # vehicles: {id: (x, y, angle, length, width, vclass)}
        self.vehicles = vehicles

    def getIDList(self):
        return list(self.vehicles.keys())

    def getPosition(self, veh_id):
        return self.vehicles[veh_id][0], self.vehicles[veh_id][1]

    def getAngle(self, veh_id):
        return self.vehicles[veh_id][2]

    def getLength(self, veh_id):
        return self.vehicles[veh_id][3]

    def getWidth(self, veh_id):
        return self.vehicles[veh_id][4]

    def getVehicleClass(self, veh_id):
        return self.vehicles[veh_id][5]

    # Inspection getters; any id not in self.vehicles raises KeyError,
    # which the interface must turn into a 'gone' marker
    def _check(self, veh_id):
        if veh_id not in self.vehicles:
            raise KeyError(veh_id)

    def getTypeID(self, veh_id):
        self._check(veh_id)
        return "car_type"

    def getSpeed(self, veh_id):
        self._check(veh_id)
        return 12.345

    def getAllowedSpeed(self, veh_id):
        return 13.9

    def getAcceleration(self, veh_id):
        return 0.8

    def getLaneID(self, veh_id):
        return "lane_0"

    def getLanePosition(self, veh_id):
        return 45.32

    def getRouteID(self, veh_id):
        return "route_0"

    def getRoute(self, veh_id):
        return ("edge_a", "edge_b")

    def getRouteIndex(self, veh_id):
        return 1

    def getDeparture(self, veh_id):
        return 10.0

    def getDepartDelay(self, veh_id):
        return 0.0

    def getWaitingTime(self, veh_id):
        return 0.0

    def getAccumulatedWaitingTime(self, veh_id):
        return 2.5

    def getTimeLoss(self, veh_id):
        return 1.25

    def getDistance(self, veh_id):
        return 1234.56

    def getLeader(self, veh_id):
        return ("veh_ahead", 12.34)

    def getNextTLS(self, veh_id):
        return (("tl0", 3, 45.06, "G"),)

    def getSpeedFactor(self, veh_id):
        return 1.0

    def getMinGap(self, veh_id):
        return 2.5


class FakeSimulation:
    def __init__(self, time=0.0):
        self.time = time
        self.scale = None

    def getTime(self):
        return self.time

    def setScale(self, value):
        self.scale = value

    def convertGeo(self, x, y):
        # A recognizable, reversible fake projection
        return 24.0 + x / 1000.0, 60.0 + y / 1000.0


class FakePhase:
    def __init__(self, duration, state):
        self.duration = duration
        self.state = state


class FakeLogic:
    def __init__(self, program_id, phases):
        self.programID = program_id
        self.phases = phases


class FakeTrafficLight:
    def __init__(self, states):
        self.states = states

    def getIDList(self):
        return list(self.states.keys())

    def getRedYellowGreenState(self, tls_id):
        return self.states[tls_id]

    def getProgram(self, tls_id):
        return "0"

    def getAllProgramLogics(self, tls_id):
        return [FakeLogic("0", [FakePhase(30.0, self.states[tls_id]),
                                FakePhase(5.0, "yyyy")])]

    def getPhase(self, tls_id):
        return 0

    def getNextSwitch(self, tls_id):
        return 130.0

    def getPhaseDuration(self, tls_id):
        return 30.0


class FakeInductionLoop:
    def __init__(self, veh_numbers, occupancies):
        self.veh_numbers = veh_numbers
        self.occupancies = occupancies

    def getIDList(self):
        return list(self.veh_numbers.keys())

    def getLastStepVehicleNumber(self, det_id):
        return self.veh_numbers[det_id]

    def getLastStepOccupancy(self, det_id):
        return self.occupancies[det_id]


class FakeTraci:
    def __init__(self, vehicles=None, time=0.0, tls=None,
                 det_veh_numbers=None, det_occupancies=None):
        self.vehicle = FakeVehicle(vehicles or {})
        self.simulation = FakeSimulation(time)
        self.trafficlight = FakeTrafficLight(tls or {})
        self.inductionloop = FakeInductionLoop(det_veh_numbers or {},
                                               det_occupancies or {})


class FakeMsg:
    def __init__(self, subject="", data=b""):
        self.subject = subject
        self.data = data
        self.responded_with = None

    async def respond(self, data):
        self.responded_with = data


def cmd_msg(command, payload=None):
    return FakeMsg(subject="sim.js266.cmd." + command,
                   data=json.dumps(payload).encode() if payload else b"")


class FakeNats:
    def __init__(self):
        self.published = []      # (subject, bytes)
        self.subscriptions = {}  # subject -> callback

    async def publish(self, subject, data):
        self.published.append((subject, data))

    async def subscribe(self, subject, cb=None):
        self.subscriptions[subject] = cb


def make_conf(net_path, **overrides):
    conf = {"scenario": "js266", "state_rate_hz": 10, "net_file": net_path}
    conf.update(overrides)
    return conf


class TestWebsumoInterface(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # A stand-in net file for every test that constructs the interface
        self.net_bytes = b"<net>fake network</net>"
        handle, self.net_path = tempfile.mkstemp(suffix=".net.xml")
        with os.fdopen(handle, "wb") as f:
            f.write(self.net_bytes)

    def tearDown(self):
        os.remove(self.net_path)

    # --- factory -----------------------------------------------------

    def test_factory_returns_none_without_conf(self):
        interface = create_websumo_interface(None, FakeTraci(), FakeNats())
        self.assertIsNone(interface)

    def test_factory_fails_at_startup_on_missing_net_file(self):
        conf = make_conf("/nonexistent/path.net.xml")
        with self.assertRaises(FileNotFoundError):
            create_websumo_interface(conf, FakeTraci(), FakeNats())

    # --- state frame -------------------------------------------------

    def test_frame_shape_field_order_and_rounding(self):
        traci = FakeTraci(
            vehicles={"veh0": (938.4123456, 169.9765432,
                               91.23456, 4.5678, 1.8123, "passenger")},
            time=123.44,
            tls={"266_Pork_Mech": "GgrrGGyy"},
            det_veh_numbers={"266_102A": 1, "266_102B": 0},
            det_occupancies={"266_102A": 0.0, "266_102B": 0.0},
        )
        interface = create_websumo_interface(
            make_conf(self.net_path), traci, FakeNats())
        frame = interface.build_state_frame()

        self.assertEqual(frame["v"], 1)
        self.assertEqual(frame["t"], 123.4)
        self.assertEqual(frame["persons"], [])
        self.assertEqual(frame["tls"], {"266_Pork_Mech": "GgrrGGyy"})
        # Occupied via vehicle number; unoccupied when both readings zero
        self.assertEqual(frame["detectors"],
                         {"266_102A": True, "266_102B": False})
        # Positional vehicle array: [id, lon, lat, angle, length, width, vclass]
        veh = frame["vehicles"][0]
        self.assertEqual(veh[0], "veh0")
        self.assertEqual(veh[1], round(24.0 + 938.4123456 / 1000.0, 7))  # lon
        self.assertEqual(veh[2], round(60.0 + 169.9765432 / 1000.0, 7))  # lat
        self.assertEqual(veh[3], 91.2)
        self.assertEqual(veh[4], 4.57)
        self.assertEqual(veh[5], 1.81)
        self.assertEqual(veh[6], "passenger")

    def test_detector_occupied_via_occupancy_alone(self):
        traci = FakeTraci(det_veh_numbers={"d1": 0},
                          det_occupancies={"d1": 12.5})
        interface = create_websumo_interface(
            make_conf(self.net_path), traci, FakeNats())
        self.assertEqual(interface.build_state_frame()["detectors"],
                         {"d1": True})

    def test_empty_simulation_frame(self):
        interface = create_websumo_interface(
            make_conf(self.net_path), FakeTraci(), FakeNats())
        frame = interface.build_state_frame()
        self.assertEqual(frame["vehicles"], [])
        self.assertEqual(frame["tls"], {})
        self.assertEqual(frame["detectors"], {})
        # The frame must always serialize
        json.dumps(frame)

    # --- publishing --------------------------------------------------

    async def test_publish_state_publishes_json_frame(self):
        nats = FakeNats()
        interface = create_websumo_interface(
            make_conf(self.net_path), FakeTraci(time=7.0), nats)
        await interface.publish_state()
        self.assertEqual(len(nats.published), 1)
        subject, data = nats.published[0]
        self.assertEqual(subject, "sim.js266.state")
        self.assertEqual(json.loads(data.decode())["t"], 7.0)

    async def test_publish_decimates_to_state_rate(self):
        nats = FakeNats()
        # 5 Hz at 0.1 s steps: every second step publishes
        interface = create_websumo_interface(
            make_conf(self.net_path, state_rate_hz=5), FakeTraci(), nats)
        for _ in range(10):
            await interface.publish_state()
        self.assertEqual(len(nats.published), 5)

    # --- net file request-reply --------------------------------------

    async def test_net_request_replies_gzipped_file(self):
        nats = FakeNats()
        interface = create_websumo_interface(
            make_conf(self.net_path), FakeTraci(), nats)
        await interface.start()
        self.assertIn("sim.js266.net", nats.subscriptions)

        msg = FakeMsg()
        await nats.subscriptions["sim.js266.net"](msg)
        self.assertEqual(gzip.decompress(msg.responded_with), self.net_bytes)

    # --- commands ----------------------------------------------------

    def make_started(self, traci=None):
        nats = FakeNats()
        interface = create_websumo_interface(
            make_conf(self.net_path), traci or FakeTraci(), nats)
        return interface, nats

    async def test_scale_command_applies_clamped(self):
        traci = FakeTraci()
        interface, _ = self.make_started(traci)
        await interface.handle_command(cmd_msg("scale", {"v": 2.0}))
        self.assertEqual(traci.simulation.scale, 2.0)
        await interface.handle_command(cmd_msg("scale", {"v": 99.0}))
        self.assertEqual(traci.simulation.scale, 5.0)

    async def test_stop_speed_and_unknown_commands_ignored(self):
        traci = FakeTraci()
        interface, nats = self.make_started(traci)
        for command in ("stop", "speed", "bogus"):
            await interface.handle_command(cmd_msg(command, {"v": 3.0}))
        self.assertIsNone(traci.simulation.scale)
        self.assertFalse(interface.paused)
        self.assertEqual(nats.published, [])

    async def test_pause_gate_passes_through_when_not_paused(self):
        interface, _ = self.make_started()
        await asyncio.wait_for(interface.pause_gate(), timeout=1)

    async def test_pause_holds_gate_and_resume_resyncs_timer(self):
        class FakeTimer:
            resyncs = 0

            def reset_time_step(self):
                self.resyncs += 1

        timer = FakeTimer()
        nats = FakeNats()
        interface = create_websumo_interface(
            make_conf(self.net_path), FakeTraci(), nats, timer=timer)

        await interface.handle_command(cmd_msg("pause"))
        self.assertTrue(interface.paused)

        gate = asyncio.ensure_future(interface.pause_gate())
        await asyncio.sleep(0.15)
        self.assertFalse(gate.done())  # step loop is held

        await interface.handle_command(cmd_msg("resume"))
        await asyncio.wait_for(gate, timeout=1)
        self.assertEqual(timer.resyncs, 1)  # no fast-forward on resume

    async def test_malformed_payload_ignored(self):
        interface, nats = self.make_started()
        await interface.handle_command(
            FakeMsg(subject="sim.js266.cmd.select", data=b"not json"))
        self.assertIsNone(interface.selected)
        self.assertEqual(nats.published, [])

    async def test_select_vehicle_one_shot_and_frame_inspect(self):
        traci = FakeTraci(
            vehicles={"veh0": (100.0, 200.0, 90.0, 4.5, 1.8, "passenger")})
        interface, nats = self.make_started(traci)
        await interface.handle_command(
            cmd_msg("select", {"kind": "vehicle", "id": "veh0"}))

        # Immediate one-shot inspect message
        self.assertEqual(len(nats.published), 1)
        one_shot = json.loads(nats.published[0][1].decode())
        self.assertEqual(one_shot["type"], "inspect")
        block = one_shot["inspect"]
        self.assertEqual(block["kind"], "vehicle")
        self.assertEqual(block["id"], "veh0")
        self.assertEqual(block["speed"], 12.35)
        self.assertEqual(block["leader"], ["veh_ahead", 12.3])
        self.assertEqual(block["nextTLS"], ["tl0", 45.1, "G"])
        self.assertEqual(block["routeEdges"], ["edge_a", "edge_b"])

        # Subsequent frames carry the inspect block too
        frame = interface.build_state_frame()
        self.assertEqual(frame["inspect"]["id"], "veh0")
        json.dumps(frame)

    async def test_select_tls_inspect_with_derived_spent(self):
        traci = FakeTraci(tls={"tl0": "GGrr"}, time=120.0)
        interface, nats = self.make_started(traci)
        await interface.handle_command(
            cmd_msg("select", {"kind": "tls", "id": "tl0"}))
        block = json.loads(nats.published[0][1].decode())["inspect"]
        self.assertEqual(block["kind"], "tls")
        self.assertEqual(block["state"], "GGrr")
        self.assertEqual(block["phases"], [[30.0, "GGrr"], [5.0, "yyyy"]])
        # spent = phaseDuration - (nextSwitch - now) = 30 - (130 - 120)
        self.assertEqual(block["spent"], 20.0)

    async def test_select_vanished_vehicle_reports_gone(self):
        interface, nats = self.make_started(FakeTraci())  # no vehicles
        await interface.handle_command(
            cmd_msg("select", {"kind": "vehicle", "id": "ghost"}))
        block = json.loads(nats.published[0][1].decode())["inspect"]
        self.assertEqual(block, {"kind": "vehicle", "id": "ghost",
                                 "gone": True})

    async def test_deselect_clears_selection(self):
        traci = FakeTraci(
            vehicles={"veh0": (0.0, 0.0, 0.0, 4.0, 2.0, "passenger")})
        interface, _ = self.make_started(traci)
        await interface.handle_command(
            cmd_msg("select", {"kind": "vehicle", "id": "veh0"}))
        self.assertIsNotNone(interface.selected)
        await interface.handle_command(cmd_msg("select"))
        self.assertIsNone(interface.selected)
        self.assertNotIn("inspect", interface.build_state_frame())


if __name__ == "__main__":
    unittest.main()
