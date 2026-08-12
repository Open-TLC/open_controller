# WebSUMO browser viewer

Simengine can stream the running simulation to a
[WebSUMO](https://github.com/Open-TLC/websumo) viewer in the browser.
It works in both simulation modes — integrated and distributed — and is
**on by default**; nothing needs to be configured for the common case.

```
OC simengine  ←TraCI/libsumo→  SUMO
     ↓ NATS  (sim.{scenario}.state)
     ↑ NATS  (sim.{scenario}.cmd.*)
WebSUMO backend  (relay, runs no SUMO of its own)
     ↕ WebSocket
   Browser
```

OC owns the simulation. WebSUMO renders what OC publishes and sends
operator commands back. The viewer keeps **no scenario files**: it
requests the network over NATS too, so nothing is shared between the two
systems except the broker.

## Running it

**Integrated mode** — a plain Python program, as always:

    python -m services.simengine.src.simengine_integrated \
        --conf-file models/testmodel/oc_demo_basic.json

**Distributed mode** — unchanged as well:

    python services/simengine/src/simengine.py \
        --conf models/JS_266_DEMO/sim/JS_266_sim_websumo.json

Either prints, on startup:

    WebSUMO interface: serving sim.{scenario}.net and publishing sim.{scenario}.state

Then start the WebSUMO backend (see its README) and open it in a
browser: the scenario appears in the list on its own, Load fetches the
network over NATS, and Start attaches to the simengine already running.

A ready-made docker stack for the distributed mode lives in
`docker-compose.websumo.yaml` at the repository root:

    docker compose -f docker-compose.websumo.yaml up --build

## Command-line options

| Option | Meaning |
|---|---|
| `--nowebsumo` | Run without the viewer (traditional mode) |
| `--nats-server` | Broker address (default `localhost`) |
| `--nats-port` | Broker port (default `4222`) |

`--nats-server` / `--nats-port` are read by both engines, matching the
other OC services. **If no broker answers, the viewer is skipped with a
warning and the simulation runs normally** — it is never allowed to stop
a simulation from running.

## Configuration

No configuration is required. Every setting defaults from the SUMO
config file the simulation is already using:

| Setting | Default |
|---|---|
| `scenario` | the sumocfg's file name without extension |
| `net_file` | the `net-file` the sumocfg loads |
| `state_rate_hz` | 10 |

To override any of them, add a top-level `websumo` block to the
simengine conf; values given there win over the defaults:

```json
"websumo": {
    "scenario": "js266",
    "state_rate_hz": 10,
    "net_file": "models/JS_266_DEMO/net/JS_266-267K.net.xml"
}
```

**The network must carry a geo-projection.** Both the viewer and OC's
own `traci.simulation.convertGeo()` need it. Check for a `<location>`
tag with a `projParameter` in the net file; a purely cartesian network
cannot be viewed.

## The NATS interface

The contract is WebSUMO's `docs/SIM_PROTOCOL.md` (version 1). OC
implements it rather than defining a dialect of its own. All of it lives
in `services/simengine/src/websumo_interface.py`.

| Subject | Direction | Payload |
|---|---|---|
| `sim.{scenario}.state` | OC → viewer | state frame, ~10 Hz |
| `sim.{scenario}.net` | viewer → OC | request-reply; reply is the gzipped `.net.xml` |
| `sim.{scenario}.cmd.*` | viewer → OC | operator commands |

### State frame

```json
{"v": 1,
 "t": 123.4,
 "vehicles": [["veh0", 24.9384, 60.1699, 91.2, 4.5, 1.8, "passenger"]],
 "persons": [],
 "tls": {"266_Pork_Mech": "GgrrGGyy"},
 "detectors": {"266_102A": true, "266_102B": false}}
```

`vehicles` is a positional array — `[id, lon, lat, angle, length, width,
vClass]` — and `detectors` maps detector id to occupancy. `persons`
(pedestrians and cyclists) is published empty for now. When an element
is selected in the browser, the frame also carries an `inspect` block.

### Commands

| Command | Effect in OC |
|---|---|
| `select` | Fills the inspection panel for a vehicle or traffic light |
| `scale` | Traffic demand multiplier (`traci.simulation.setScale`, clamped 0–5) |
| `pause` / `resume` | Holds and releases the simulation step loop |
| `speed`, `stop`, `spawn` | **Ignored** (see below) |

Unknown or malformed commands are ignored, as the protocol prescribes.

**Known limitation — pause and the controller.** Pausing holds the
*simulation*. In distributed mode the control engine is a separate
process synced to wall-clock time and does not hear these commands, so
signals keep cycling while the simulation is held; on resume the phase
has moved on. Making the controller follow is future work and belongs
with a wider controller UI. `speed` is ignored for the same reason
(plus it would need the timer's pacing changed mid-run), and `stop`
because the restart story is unclear when the viewer merely attaches to
a simengine it did not start.

`spawn` needs the scenario's route file, which OC does not serve yet —
see below.

### Not served yet

The protocol also defines `sim.{scenario}.detectors` and
`sim.{scenario}.routes`, request-reply subjects carrying the detector
and route XML. OC does not answer them, so the viewer draws no detector
bars and no vehicle-injection markers; everything else renders. Adding
them is small but not free: OC models split these across several files
(`JS_266_e1dets.add.xml` + `JS_267_e1dets.add.xml`; separate car, tram
and bike route files), while the protocol carries **one document per
subject**, so the simengine must merge them into a single `<additional>`
root before replying.

## How it is put together

The interface is one module, `websumo_interface.py`, and it is the only
place that touches WebSUMO's subjects. It is deliberately **not** an
`outputs.py` plugin: an *output* in OC's sense is operational data the
controller produces — detector statuses, group statuses, radar
detections — consumed by other components. This stream is a rendering
surface, the same way `sumo-gui`'s X11 traffic is not an OC output.
Nothing in OC consumes it and no OC behaviour depends on it.

The two engines drive the same interface differently, because they are
built differently:

- **`simengine.py`** is asyncio throughout and already holds a NATS
  connection, so it simply awaits the interface's coroutines in its step
  loop.
- **`simengine_integrated.py`** is a synchronous loop with no asyncio of
  its own, so it owns an event loop and runs those same coroutines to
  completion. No threads are involved, which also means the command
  callbacks run on the thread that steps SUMO — necessary, because
  libsumo is not thread safe.

One integrated-mode detail worth knowing: that engine paces itself with
its own `next_update_time` accumulator, so after a pause it restarts
pacing from the current time. Without that, the loop would run flat out
until it caught up with the wall clock — a 4 s pause replayed as roughly
7 simulated seconds in 3.

Unit tests are in `tests/test_websumo_interface.py`. The traci module
and the NATS client are constructor arguments, so the tests run without
SUMO and without a broker.
