"""Unit tests for the WebSUMO viewer interface.

The traci module and the NATS client are constructor arguments of the
interface, so these tests run without SUMO or a broker: FakeTraci serves
canned simulation state, FakeNats records what would go on the wire.
The frame assertions follow WebSUMO's SIM_PROTOCOL.md (version 1).
"""

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


class FakeSimulation:
    def __init__(self, time=0.0):
        self.time = time

    def getTime(self):
        return self.time

    def convertGeo(self, x, y):
        # A recognizable, reversible fake projection
        return 24.0 + x / 1000.0, 60.0 + y / 1000.0


class FakeTrafficLight:
    def __init__(self, states):
        self.states = states

    def getIDList(self):
        return list(self.states.keys())

    def getRedYellowGreenState(self, tls_id):
        return self.states[tls_id]


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
    def __init__(self):
        self.responded_with = None

    async def respond(self, data):
        self.responded_with = data


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


if __name__ == "__main__":
    unittest.main()
