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
- subscribing to `sim.{scenario}.cmd.*` and applying operator commands
- all subject-name construction for this feature

It exposes a small surface to the rest of OC — roughly a class with
`connect()`, `publish_state()` and `apply_pending_commands()`, plus a
factory that returns `None` when the feature is not configured, so call
sites are a single guarded line.

Nothing else in OC imports SUMO or NATS *for this feature*, and this
module imports nothing from OC's control engine.

## The only OC files touched

| File | Edit |
|---|---|
| `services/simengine/src/websumo_interface.py` | **new** — all of it |
| `services/simengine/src/simengine.py` | construct the interface if configured; call publish + apply around the existing `simulationStep()` |
| `services/simengine/src/simengine_integrated.py` | same two call sites, in `run_sumo()`'s main loop (around line 278) |
| `tests/test_websumo_interface.py` | **new** — unit tests |
| a simengine conf + `docker-compose.yaml` | one conf block, one service |

`outputs.py`, `confread.py`, `timer.py`, the whole `control_engine`
tree, and every existing conf are **untouched**. If a diff shows
otherwise, principle 1 or 2 has been broken.

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

The payload is already fixed by WebSUMO's `_do_step()`
(`backend/sumo_adapter.py`), and OC matches it rather than inventing a
dialect:

```json
{"t": 123.4,
 "vehicles": [["veh0", 24.9384, 60.1699, 91.2, 4.5, 1.8, "passenger"]],
 "tls": {"266_Pork_Mech": "GgrrGGyy"},
 "det_on": ["266_102A"],
 "events": []}
```

`vehicles` is a positional array — `[id, lon, lat, angle, length, width,
vClass]`. Everything needed is already read from SUMO elsewhere in
simengine (vehicle geo positions in `outputs.py:update_radars()`,
occupancy in `DetStorage`); the new module reads it directly rather than
reaching into those classes.

**No WebSUMO code change in this step** — `main.py` already subscribes to
`sim.{scenario}.state` and relays it to the browser.

Enabled by one conf block; omit it and the feature does not exist:

```json
"websumo": { "scenario": "js266", "state_rate_hz": 10 }
```

## Step 2 — Operate

Subscribe to `sim.{scenario}.cmd.*` and apply the browser's commands
(pause, resume, speed, scale, spawn) before the next step.

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

WebSUMO's `main` currently has **no Dockerfile**. Needs one for backend +
built frontend, and a `websumo` service in OC's compose with `NATS_URL`
and a scenario directory mounted. In OC mode the adapter never runs, so
the image needs no `libsumo`/`eclipse-sumo` — only `sumolib` for the map
GeoJSON.

OC's existing `nats` service is the only broker. No leaf nodes, no
subject bridging: `NATS_TOPOLOGY_RESEARCH.md` recommends leaf nodes for
joining two separate brokers, which does not apply here.

## Tests

`tests/test_websumo_interface.py`, `unittest` style like the rest of
`tests/`, no SUMO or NATS required — traci and the NATS client are
injected, so the module is testable in isolation. That testability is a
reason for the single-file design, not an afterthought.

Covers: state frame shape and field order against the contract above;
rounding; empty simulation; command parsing and rejection of unknown
commands; and that a disabled interface performs no calls at all.

## Open decisions (not to be settled unilaterally)

1. **Scenario discovery.** `main.py:184` gates the WebSocket on
   `_is_valid_scenario()`, which requires a `{scenario}.sumocfg` on disk.
   In OC mode nothing reads that file, but without one the viewer refuses
   to connect. Keep a stub, or change the predicate? WebSUMO-side call.
2. **Build or pull.** Build the websumo image from the repo in compose,
   or publish an image and pull it?
3. **Scope of "operate".** Which of pause/resume/speed/scale/spawn are
   actually wanted in phase 1.

## Required on the WebSUMO side (their repo, their commits)

`TODO.md` item 1 and README's *"Planned (for Open Controller
integration)"* currently document **Option 2** — the adapter as a
drop-in replacement for OC's `simengine_integrated.py`, republishing
`detector.control.*` and applying `group.control.*`. That is the
opposite of this plan. Until it is corrected, work in that repo will
rebuild the wrong integration and be right to, by its own docs.
