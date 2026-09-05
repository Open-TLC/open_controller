# Open Controller — bug reports

Bugs found while integrating Open Controller with externally-generated configs
(graph2sumo → `oc_controller.json` → `simengine_integrated.py`). Filed here as
docs (no issue tracker access from the integration environment).

---

## B-1 · `sumo.graph: true` forces SUMO-GUI regardless of DISPLAY — headless runs fail

**Component:** `services/simengine/src/simengine_integrated.py` (`run_sumo`, ~lines 223–231)
**Severity:** blocker for headless / server / CI runs
**Found:** 2026-09-05, OC `main` @ `7285614`, running the integrated simengine on a
headless host (no X server).

**Symptom.** With a config whose `sumo` section has `"graph": true`, the integrated
simengine launches the **`sumo-gui`** binary. On a headless host it cannot open a
display and dies, then TraCI never connects:

```
FXApp::openDisplay: unable to open display :0.0
UserWarning: Could not connect to TraCI server using port NNNNN
             (TraCI server already finished). Retrying with different port.
```

…looping forever over new ports (the GUI never starts, so TraCI never comes up).

**Root cause.** The binary is chosen **only** from `sys_cnf['sumo']['graph']`; the
`display_available` value is computed but **never used**, so the code does not fall
back to the non-GUI binary when there is no display. The inline comment says the
opposite of what the code does:

```python
# Check whether the display is available before using gui
display_available = os.environ.get('DISPLAY') is not None and os.environ.get('DISPLAY') is not ''

# Graph always if set in conf, and also if param says so, but not if display is not available
if sys_cnf['sumo']['graph']:
    sumo_bin = SUMO_BIN_NAME_GRAPH      # sumo-gui — chosen even when display_available is False
else:
    sumo_bin = SUMO_BIN_NAME
```

**Fix.** Gate the GUI binary on `display_available` (as the comment intends):

```python
if sys_cnf['sumo']['graph'] and display_available:
    sumo_bin = SUMO_BIN_NAME_GRAPH
else:
    sumo_bin = SUMO_BIN_NAME
```

**Workaround.** Set `"graph": false` in the config for headless runs.

---

## B-2 · Always-true identity test against a string literal (`is not ''`) → SyntaxWarning

**Component:** `services/simengine/src/simengine_integrated.py` (~line 224)
**Severity:** minor (correctness smell + Python `SyntaxWarning`)

**Symptom.** On import/run:

```
SyntaxWarning: "is not" with 'str' literal. Did you mean "!="?
  display_available = os.environ.get('DISPLAY') is not None and os.environ.get('DISPLAY') is not ''
```

**Root cause.** `x is not ''` compares object **identity** with a str literal, which
is always `True` (CPython may intern the empty string, but this is not guaranteed
and is not what's intended). So `display_available` is effectively just
`os.environ.get('DISPLAY') is not None` — an unset `DISPLAY` is handled, but a
present-but-empty `DISPLAY` is treated as available.

**Fix.** Use a value comparison, or just truthiness:

```python
display_available = bool(os.environ.get('DISPLAY'))
```

(Fixing B-2 also gives B-1 the correct `display_available` for its gate.)
