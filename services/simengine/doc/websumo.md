# WebSUMO viewer interface

OC runs the simulation; this interface publishes the simulation state to
a NATS server so it can be watched with the WebSUMO browser viewer. It
is viewing only: the viewer never controls the simulation, and if the
interface fails for any reason the simulation runs on unaffected.

All interface code is in one file, `src/websumo_interface.py`. The two
engines call it from three places each: start (after SUMO starts),
publish (in the engine's own update tick), end (at loop exit).

## NATS subjects

The protocol is defined by WebSUMO (`docs/SIM_PROTOCOL.md` in the
websumo repository, v 1.0). Scenario name = the sumocfg file name
without suffix (e.g. `JS270_med_traffic`).

| Subject                    | Direction     | Content                                     |
|----------------------------|---------------|---------------------------------------------|
| `sim.{scenario}.state`     | publish       | per-tick snapshot: vehicles, persons, tls, detectors |
| `sim.{scenario}.log`       | publish       | collisions, teleports, emergency stops      |
| `sim.{scenario}.end`       | publish       | once, when the simulation ends              |
| `sim.{scenario}.net`       | request-reply | the gzipped net file                        |
| `sim.{scenario}.detectors` | request-reply | gzipped merged e1 detector files            |
| `sim.{scenario}.cmd.select`| subscribe     | selected element's details go into the state |

The run control commands (`cmd.pause`, `resume`, `stop`, `speed`,
`scale`, `spawn`) are deliberately ignored: the engine's timer owns the
cadence. The viewer's pause/speed buttons therefore do nothing.

The net file and the detector files are derived from the sumocfg the
conf already points at; the e1 detectors of all additional files are
merged into one document. The viewer needs nothing on its own disk.

## Requirements

- A NATS server. Address resolution, in order: `--nats-server` /
  `--nats-port` command line params, the conf file's `nats` section,
  `localhost:4222`.
- **A geo-referenced net.** WebSUMO renders in WGS84; the net must have
  a real `projParameter` in its `<location>` element. A synthetic net
  (`projParameter="!"`) disables the interface at the first publish. A
  synthetic net can be geo-referenced by borrowing the `<location>`
  line of a real model.
- For real-time viewing, use `"timer_mode": "real"` in the conf's timer
  section. In `fixed` mode the engine runs at full CPU speed and the
  viewer shows a fast-forward simulation — the interface adds no timing
  of its own, ever.

## Failure behaviour

- No NATS server at startup: one warning, the engine runs without the
  viewer. Nothing else changes.
- Any error while reading the state: one warning, the interface
  disables itself, the engine runs on.
- `--nowebsumo` skips the interface entirely.

## Running: integrated mode

A plain python command — not docker:

    pipenv run python services/simengine/src/simengine_integrated.py \
        --conf-file models/testmodel/oc_demo_basic.json

The NATS broker and the viewer are run separately, e.g. from the
compose file: `docker compose up nats websumo`. Then open
`http://localhost:8775`, pick the scenario, Load, Start.

Optional flags: `--nats-server`, `--nats-port`, `--nowebsumo`.

## Running: the container stack

    docker compose up

brings up everything: nats, the controller, the UI, indicators, the
independent engine (`simengine.py`, also with this interface) and the
websumo viewer on port 8775. The websumo image is self-contained: the
build clones the public Open-TLC/websumo repository, nothing outside
this repository is needed.

After pulling new code, rebuild — `docker compose up` never rebuilds
images by itself:

    docker compose down
    docker compose build
    docker compose up

New websumo commits: `docker compose build --no-cache websumo`.

## Troubleshooting

- **No scenario in the viewer's list**: nothing is publishing. Check
  `docker logs oc_simengine_container` for the line
  `WebSUMO interface publishing scenario ... to nats://...`. If the
  line is missing, the image is stale (rebuild, see above). If it says
  `Warning: running without WebSUMO - could not connect`, the broker
  was not reachable at startup (the printed exception says why).
- **Verify the stream directly**: `nats sub "sim.>"` — a healthy engine
  produces ~10 messages/s.
- **Port conflicts**: 4222 (nats) and 8775 (viewer) must be free on the
  host; an old container or a native nats-server holds them silently.
- **Windows**: `.gitattributes` forces LF endings on the shell scripts;
  the container entrypoints break on a CRLF checkout. Docker Desktop's
  restart button never picks up a rebuilt image — use
  `docker compose up` from a terminal.
- **Viewer loads but Load fails with a geo-projection error**: the net
  is not geo-referenced, see Requirements.
