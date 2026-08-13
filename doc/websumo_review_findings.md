# WebSUMO branch review findings

Code review of `feat/websumo` vs `main` (2026-08-13, high effort: 8
finder angles, adversarial verification; 3 candidates refuted, 10
survived). Worklist — update the Status column as items are resolved.

## Correctness (verified)

| # | Where | Finding | Status |
|---|-------|---------|--------|
| 1 | `simengine.py:39`, `simengine_integrated.py` | libsumo cannot run sumo-gui: `--graph` / conf `"graph": true` hard-aborts the interpreter (uncatchable C++ abort) on any headless host. Confs `oc_demo_full_features.json` and `JS1_266_DEMO_042026P.json` still set it. Fix: warn and run headless — WebSUMO is the viewer. | fixed |
| 2 | `websumo_interface.py:205` | `_publish` discards the future, so a mid-run broker outage is never detected: no warning, `connected` stays True, per-tick extraction keeps running for a dead link. Fix: done-callback that disables on publish failure. | fixed |
| 3 | `simengine_integrated.py:134`, `confread_ms.py` | Conf-file `"nowebsumo": true` can never work: the argparse `store_true` default `False` survives the None-filter and overwrites the conf value. Fix: `default=None`. (Note: `--graph`/`--print-status` have the same pre-existing quirk, out of scope here.) | fixed |
| 4 | `websumo_interface.py:359` | Scenario identity is the sumocfg basename only: two engines on the same sumocfg + broker publish interleaved state on the same subjects and both answer `.net`. Viewer shows one flickering scenario. Options: instance suffix in the scenario name (changes discovery contract) or document "one engine per scenario per broker". | open — needs a decision |
| 5 | `simengine.py:281`, `simengine_integrated.py:300` | `publish_end()`/`close()` are on the straight-line exit only (no try/finally): an exception escaping the loop skips the end message and the drain. In integrated, the *unguarded* second `setRedYellowGreenState` (line 236) is a live trigger. Fix: try/finally around the loops — first non-additive engine edit, so deliberate. | open — needs a decision |
| 6 | `websumo_interface.py:79` | Space in the sumocfg name → illegal NATS subject → `BadSubjectError` misreported as "no NATS server". Fix: validate the scenario token, print the real exception. | fixed |

## Cleanups / design tradeoffs

| # | Where | Finding | Status |
|---|-------|---------|--------|
| 7 | `websumo_interface.py:410` | `nats_conf_from_sys_conf()` duplicates the CLI-over-conf NATS merge that `confread.py` already implements, and hardcodes confread_ms's quirk of merging CLI params into the `sumo` section. Proper fix: give `confread_ms.GlobalConf` a `get_nats_params()` and delete the helper. Increases coupling to confread — decide deliberately. | open |
| 8 | `docker-compose.yaml:74` | websumo image build cloned unpinned upstream HEAD: an upstream push could break `docker compose up` with no change in this repo, non-reproducibly (layer cache). Fixed by pinning `WEBSUMO_REF`; bump it deliberately to take a newer viewer. Longer term: a real `services/websumo/docker/Dockerfile`. | fixed (pin) |
| 9 | `websumo_interface.py:217` | ~1200 libsumo calls per 0.1s tick at 200 vehicles; static fields (length, width, vclass) re-fetched 10×/s; json.dumps on the engine thread. Fix (subscriptions + caching) collides with "obvious over fast" — only act if the tick budget measurably suffers. | open — deferred on purpose |
| 10 | `simengine.py:182` | The async engine opens a second NATS connection + thread although it owns a connected client on its loop. Fix couples the interface to the engine's event loop — separation was chosen deliberately. | open — deferred on purpose |
| 11 | `outputs.py`, `simengine.py` | Dead `import os`/`import sys` left behind by the traci-block removals. | fixed |
| 12 | `websumo_interface.py:78` | The CRLF `.strip()` on the sumocfg path is a band-aid for a corrupted argument; `.gitattributes` is the real fix, the strip stays as defense. | accepted as-is |

## Refuted during verification (for the record)

- `nats_url` scheme mangling — input shape unreachable.
- `timer_mode` fixed→real conf edits as regression — clockwork never
  reads `timer_mode`; fixed-mode confs remain available.
- `JS1_266_DEMO_042026P.json` NATS repoint as breakage — no consumers
  rely on the old address; launchers pass `--nats-server`.
