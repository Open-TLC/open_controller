# WebSUMO integration plan (OC side)

*2026-08-12. Implements **Option 3** of WebSUMO's
`docs/INTEGRATION_ROADMAP.md`: OC's simengine is the simulation master,
WebSUMO is a pure NATS subscriber with no TraCI connection of its own.*

```
OC simengine  ←TraCI/libsumo→  SUMO
     ↓ NATS  (sim.{scenario}.state)
     ↑ NATS  (sim.{scenario}.cmd.*)
WebSUMO backend  (FastAPI relay, no SUMO)
     ↕ WebSocket
   Browser
```

## Goal

Make it possible to **view and operate** an OC simulation in the browser
through WebSUMO. OC keeps owning SUMO. WebSUMO renders what OC publishes
and sends operator commands back.

## Principles

These are binding. If a step appears to require breaking one, the step is
wrong.

1. **No changes to existing OC operations.** We only *add* new
   communication subjects. Nothing in OC's current behaviour — control
   logic, existing subjects, existing confs, detector handling, signal
   application — changes. With the interface switched off, OC behaves
   exactly as it does today, byte for byte.

2. **Maximum separation from the rest of OC.** This interface is its own
   thing with its own lifecycle. It does not spread into OC's modules,
   and OC's modules do not depend on it. It can be deleted by removing
   one file and a handful of call sites.

3. **Clean, readable code in OC's idiom — over cleverness.** Follow the
   conventions already in `services/simengine/src/`. No performance
   tricks, no compressed one-liners, no abstraction invented for this
   feature. If a choice is between "fast" and "obvious", pick obvious.

4. **All interface code lives in one file, and it is tested.** Every
   traci↔NATS operation for this feature is implemented in a single new
   module. The only edits elsewhere are the call sites that invoke it.

## The one file

`services/simengine/src/websumo_interface.py`

It owns, and is the only place that contains:

- building the state frame from SUMO (vehicles, TLS, detectors)
- publishing it on `sim.{scenario}.state`
- answering `sim.{scenario}.net` file requests (gzipped bytes, see step 1)
- subscribing to `sim.{scenario}.cmd.*` and applying operator commands
- all subject-name construction for this feature

It exposes a small surface to the rest of OC — roughly a class with
`connect()`, `publish_state()` and `apply_pending_commands()`, plus a
factory that returns `None` when the feature is not configured, so call
sites are a single guarded line. The traci-like module and the NATS
client are constructor arguments, not imports — the two engines bind
SUMO differently (TraCI vs libsumo), and injection is what lets the
tests run without SUMO or a broker.

Nothing else in OC imports SUMO or NATS *for this feature*, and this
module imports nothing from OC's control engine.

## The only OC files touched

| File | Edit |
|---|---|
| `services/simengine/src/websumo_interface.py` | **new** — all of it |
| `services/simengine/src/simengine.py` | construct the interface if configured; call publish + apply around the existing `simulationStep()` |
| `services/simengine/src/confread.py` | **3 additive lines**: pass the `websumo` conf section through, plus a `get_websumo_params()` accessor returning `None` when absent (see below) |
| `services/simengine/src/simengine_integrated.py` | later step — see "The two engines are different animals" |
| `tests/test_websumo_interface.py` | **new** — unit tests |
| a simengine conf + `docker-compose.yaml` | one conf block, one service |

`outputs.py`, `timer.py`, the whole `control_engine` tree, and every
existing conf are **untouched**. If a diff shows otherwise, principle 1
or 2 has been broken.

**Why `confread.py` must be touched** (found in review, 2026-08-12):
`GlobalConf.set_vals_from_conf` copies the conf file section by explicit
section — `simulation`, `radars`, `outputs` (only `det`/`sig`/`rad`),
`inputs` (only `sig_inputs`). An unknown top-level `websumo` block would
be **silently dropped**. Nesting our config inside `simulation` (whose
`.update()` would let it through) was rejected as exactly the kind of
trick principle 3 bans. So `confread.py` gets one more `if 'websumo' in
config_from_file:` passthrough in its existing section-by-section idiom.
Purely additive; no existing key's handling changes.

### The two engines are different animals (found in review, 2026-08-12)

The plan originally said "same two call sites" in both engines. The code
says otherwise:

- **`simengine.py`** is asyncio end to end: it already holds a NATS
  connection, and its run loop (`simengine.py:233-280`) awaits
  `send_statuses_to_nats()` right after each `simulationStep()`. Our two
  call sites drop in naturally, and the interface publishes on the
  connection pattern the file already uses. **Step 1 targets this engine
  only.**
- **`simengine_integrated.py`** is fully synchronous — a `while` /
  `time.sleep` loop with **no NATS connection anywhere** and no asyncio.
  Since `nats-py` is asyncio-only, publishing from it needs an event
  loop in a background thread behind a small synchronous facade. That
  facade lives inside `websumo_interface.py` like everything else, but
  it is real machinery, so integrated-mode support is a **separate later
  step**, done after the async path has proven the frame — not smuggled
  into step 1.

One consequence for the module's design: the two engines also bind SUMO
differently (`simengine.py` imports TraCI from `SUMO_HOME`;
`simengine_integrated.py` uses libsumo on Linux/macOS). The module
therefore takes the traci-like module as a constructor argument instead
of importing it — which is also what makes the unit tests possible
without SUMO.

Checked and safe: `simengine_integrated.py` reads controllers from the
explicit `"controllers"` section of its conf (`_create_controllers`),
not by iterating top-level keys, so a top-level `websumo` block in that
conf collides with nothing. (Its conf reader is `confread_ms.py`, which
passes the whole dict through unfiltered — no change needed there.)

### Why this is not an `outputs.py` plugin

`outputs.py` stays exactly as it is, and this feature is deliberately
**not** registered in its `OUTPUT_TYPES` table.

An *output* in OC's sense is operational data the controller produces as
part of doing its job — detector statuses, signal group statuses, radar
detections — consumed by other OC components and meaningful to the
system's behaviour. The WebSUMO stream is none of that. It is a **user
interface surface**: pixels-in-waiting for a human looking at a screen.
Nothing in OC consumes it, and no OC behaviour depends on it.

The analogy is SUMO's own GUI. When `sumo-gui` renders the simulation
over X11, that X11 traffic is not one of OC's outputs — it is how a
person watches the simulation. WebSUMO is the same thing over NATS and a
browser instead of X11 and a local display. Putting it in `outputs.py`
would classify a viewport as controller data.

So the separation is categorical, not merely a concession to principle 2
— though it serves that too: the feature keeps its own lifecycle and
stays deletable as one file.

(The naming can read oddly at first glance, since "output" is a broad
word and this does technically leave the process. The distinction that
matters is *operational data* versus *rendering surface*.)

## Step 1 — View

OC publishes the state frame; the browser renders it. Pure addition:
nothing in OC reads this frame, so with the conf block absent, not one
code path changes.

The payload is now **frozen by WebSUMO as `docs/SIM_PROTOCOL.md`
(v1.0, 2026-08-11)** — the canonical contract, versioned via a `v`
field. OC implements it rather than inventing a dialect:

```json
{"v": 1,
 "t": 123.4,
 "vehicles": [["veh0", 24.9384, 60.1699, 91.2, 4.5, 1.8, "passenger"]],
 "persons": [],
 "tls": {"266_Pork_Mech": "GgrrGGyy"},
 "detectors": {"266_102A": true, "266_102B": false},
 "events": []}
```

Required fields: `v`, `t`, `vehicles`, `persons`, `tls`, `detectors` —
empty containers when nothing to report. `vehicles` is a positional
array `[id, lon, lat, angle, length, width, vClass]`; `persons`
(pedestrians/cyclists) is `[id, lon, lat, angle, speed]` and phase 1
publishes it empty. Note **`detectors` is an object `{id: bool}`**, not
the occupied-id list an earlier draft of this plan had. Optional fields
(`events`, `maxRate`, `_empty`, `inspect`) are omitted in phase 1.

Everything needed is already read from SUMO elsewhere in simengine
(vehicle geo positions in `outputs.py:update_radars()`, occupancy in
`DetStorage`); the new module reads it directly rather than reaching
into those classes.

**No WebSUMO code change in this step** — `main.py` already subscribes to
`sim.{scenario}.state` and relays it to the browser.

`main.py` also subscribes to `sim.{scenario}.log` and `.end`. Neither is
needed to render, so phase 1 publishes only `.state`; `.end` when a run
finishes is a cheap later addition if the viewer should show it.

**The network file travels over NATS too** (protocol addition,
2026-08-12, on WebSUMO `main`): the viewer holds no scenario files at
all. The module answers request-reply on `sim.{scenario}.net` with the
**gzip-compressed** bytes of the net file named in the conf — opaque
bytes, never parsed by OC; the sumolib→GeoJSON rendering stays on
WebSUMO's side. JS_266's net is 55 KB gzipped, far under the 1 MB NATS
payload cap. `sim.{scenario}.detectors` / `.routes` are optional
equivalents we do **not** serve in phase 1 (see open questions).

Discovery is closed by the same protocol change: a scenario is
discoverable as soon as `.state` is published (the viewer watches
`sim.>`), Load fetches the net over NATS, and Start **attaches** to the
already-running simengine — it never spawns or kills one. No `.sumocfg`,
no `SCENARIOS_DIR`, no scenario wrapper directory anywhere in OC.

Enabled by one **top-level** conf block in the simengine conf; omit it
and the feature does not exist (`get_websumo_params()` returns `None`
and no interface object is ever constructed):

```json
"websumo": {
    "scenario": "js266",
    "state_rate_hz": 10,
    "net_file": "models/JS_266_DEMO/net/JS_266-267K.net.xml"
}
```

The net must carry a geo projection — `traci.simulation.convertGeo()`
(vehicle lon/lat) and the viewer both require it. Verified 2026-08-12:
`JS_266-267K.net.xml` has a full `<location>` tag (UTM 35 / WGS84).
Check that tag first when wiring a new model; a purely cartesian net
cannot be viewed.

## Step 2 — Operate

Subscribe to `sim.{scenario}.cmd.*` and apply the browser's commands
before the next step. The command set, payloads, and semantics are
defined in `SIM_PROTOCOL.md`: `pause`, `resume`, `stop`, `speed`
(`{"v": float}`, clamped to 0.1–1000), `scale` (`{"v": float}`, 0–5),
`select`, `spawn`. Its prescribed step flow — collect pending commands,
apply, step, publish — matches where our two call sites already sit.
Malformed or unsupported commands are silently ignored, per the
protocol.

This is the one place needing care: pause and speed act on the step loop,
which is existing OC behaviour. To honour principle 1, the loop gains
**no conditionals of its own** — it calls one method on the interface
object, and all decision-making lives inside the module. When the
interface is absent the call site is skipped entirely, so the loop is
unchanged.

If any command cannot be applied without restructuring OC's timer, it is
dropped from scope rather than worked around. Viewing (step 1) is
independently useful and must not be held up by it.

## Step 3 — Docker

Same procedure as OC's own services — one `build:` service entry in
`docker-compose.yaml` — except the build context is the public WebSUMO
repo instead of a local Dockerfile path, so **no local websumo checkout
is needed**:

```yaml
  websumo:
    image: websumo
    container_name: oc_websumo_container
    profiles: ["websumo"]          # off by default; principle 1 applies
                                   # to deployment too
    build:
      context: https://github.com/Open-TLC/websumo.git   # pin a tag when one exists
    ports:
      - "8776:8775"
    environment:
      - NATS_URL=nats://nats:4222
    depends_on:
      - nats
```

- **No volumes, no `SCENARIOS_DIR`** — the file-less protocol
  (2026-08-12) removed the viewer's entire filesystem footprint. The
  backend runs with an empty scenario directory and fetches the net over
  NATS. NATS subjects are now the *only* surface between the two
  systems: nothing shared but the broker.
- `profiles: ["websumo"]` keeps it separable: a plain
  `docker compose up` starts exactly today's stack;
  `docker compose --profile websumo up` adds the viewer. Removing the
  integration = deleting this one service entry.
- **Prerequisite on WebSUMO's `main`: a Dockerfile** (verified still
  missing 2026-08-12). Their `run.sh` documents the runtime deps:
  backend needs the SUMO distribution for `sumolib` + binaries (their
  standalone adapter also uses `libsumo`), frontend is a node build.
  The image serves both, exposes 8775, honours `NATS_URL`.

**The image keeps `libsumo`/`eclipse-sumo`.** WebSUMO's docs (2026-08-12)
state that `sumo_adapter.py` remains its *standalone, no-OC simengine* —
so the simulator must stay installed for WebSUMO to run without us.
Integrated mode simply never starts the adapter; it is a runtime mode,
not a build-time removal. Stripping the simulator from the image would
break WebSUMO's standalone capability, which is the exact risk its
Option 3 write-up warns about.

OC's existing `nats` service is the only broker. No leaf nodes, no
subject bridging: `NATS_TOPOLOGY_RESEARCH.md` recommends leaf nodes for
joining two separate brokers, which does not apply here.

## Tests

`tests/test_websumo_interface.py`, `unittest` style like the rest of
`tests/`, no SUMO or NATS required — traci and the NATS client are
injected, so the module is testable in isolation. That testability is a
reason for the single-file design, not an afterthought.

Covers: state frame shape and field order against the contract above;
rounding; empty simulation; the `.net` request-reply (gzipped bytes of
the conf-named file, request payload ignored); command parsing and
rejection of unknown commands; and that a disabled interface performs
no calls at all.

## Open decisions (not to be settled unilaterally)

1. ~~**Scenario discovery.**~~ Closed 2026-08-12 by the file-less
   protocol: publishing `.state` is discovery; no `.sumocfg` needed.
2. **Build or pull.** Build the websumo image from the repo in compose,
   or publish an image and pull it? (Blocked on their Dockerfile either
   way.)
3. **Scope of "operate".** Which of pause/resume/speed/scale/spawn are
   actually wanted in phase 1.
4. **Serving `.detectors` / `.routes`.** Deferred from phase 1 — without
   them the viewer renders no detector bars and no spawn markers
   (occupancy and signals are unaffected; they ride the state frame).
   Serving them later needs one real piece of logic: OC's model splits
   detectors and routes across several files (`JS_266_e1dets.add.xml` +
   `JS_267_e1dets.add.xml`; cars/trams/bikes route files), and the
   protocol wants one document per subject — so a small XML merge, or a
   conf listing exactly one file per subject. Decide when the features
   are wanted. Note: if spawn markers stay unserved, dropping the
   `spawn` command from step 2's scope follows naturally.

## Agreed on the WebSUMO side

Confirmed 2026-08-12 in WebSUMO commits `4965e39` and `55897b1`:

- `docs/INTEGRATION_ROADMAP.md` — *"Decision (2026-08-12): Option 3. OC's
  simengine owns the simulation and publishes `sim.{scenario}.state`;
  WebSUMO subscribes and renders, and does not run SUMO in integrated
  mode."* Options 2 and 4, and the `detector.control.*` /
  `group.control.*` bridge, are recorded as not planned.
- `docs/SIM_PROTOCOL.md` — the frozen v1 contract this plan's frame and
  commands are written against.
- `backend/simbridge.py`, `docs/INTEGRATING_WITH_OC.md`,
  `docs/OC_INTEGRATION_HANDOFF.md` — WebSUMO's offered implementation
  path (see below).

### simbridge.py: reference, not dependency

WebSUMO ships `backend/simbridge.py` — the background-thread NATS facade
with serializer helpers — and its guide says "copy simbridge.py into
your repo". This plan **does not vendor it**; `websumo_interface.py`
stays OC's own code, for the reasons the principles already give: it
must live OC's lifecycle, carry OC's tests, and follow OC's idiom (its
serializers also assume `sumolib` net loading, where OC uses traci's
`convertGeo` and needs no extra dependency). WebSUMO's own handoff
blesses this: *"Protocol-first: the contract is the NATS subject schema,
not the code. OC can reimplement the bridge if needed."* simbridge.py is
the reference implementation to check against — particularly its thread
facade, when the later `simengine_integrated.py` step needs one.

### Closed by WebSUMO's file-less protocol (2026-08-12)

A later series on their `main` (through `ac115e4`) made NATS-only the
primary documented mode and closed two of this plan's open items:

- **Static files over NATS**: `sim.{scenario}.net` / `.detectors` /
  `.routes` request-reply subjects, gzipped replies, empty request
  payload, timeout ⇒ artifact absent ⇒ render without that overlay.
  Only `.net` is required. Raw XML travels (not GeoJSON), so OC ships
  files it already has and WebSUMO owns the rendering.
- **Scenario discovery**: watching `sim.>` for `.state` — publishing
  state *is* discovery. `list_scenarios()` = local ∪ live-on-NATS, and
  Start attaches to an external simengine instead of spawning one.
- Also fixed there: the lon/lat ordering slip in the protocol's example,
  and a simbridge stay-alive bug.

### Still open on the WebSUMO side

- **No Dockerfile on `main`** (verified again 2026-08-12) — step 3's
  prerequisite stands; `run.sh` now documents the runtime deps an image
  needs.
