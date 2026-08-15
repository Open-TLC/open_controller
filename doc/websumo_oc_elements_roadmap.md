# WebSUMO: displaying OC control-plane elements — our side

WebSUMO's `docs/OC_ELEMENTS_DISPLAY_PLAN.md` (2026-08-14, "considered, not
yet scheduled") proposes showing OC's control plane — signal groups, phase
ring/intergreens, indicators, detector roles, controller state machine — on
top of the SUMO network view, which today only shows raw TLS/detector
state. This is genuinely new value (OC's own Dash UI has no map) and their
first slice is explicitly **zero OC changes**: subscribe directly to our
existing `group.status.*` / `detector.status.*` / `group.e3.*` subjects and
join them against our model conf file.

Not scheduled on their side; nothing to do on ours yet. Landing this here
so the open questions are known when it reaches our table — likely once
their P1 (groups on the map + group inspector) is built and they want the
richer controller-state fields their plan flags as "not on the wire yet"
(Option B/C: OC publishing an overlay). See also [[websumo-is-viewer-only]]
and [[websumo-diff-first-contract]] for the standing principles this work
would need to keep.

## Issues verified against our own code, for whoever picks this up

Their plan's assumptions were checked against the actual OC repo, not just
read at face value. Three gaps worth knowing before their Option A/B/C
decision is made for real:

1. **OC's native subjects have zero scenario/instance scoping — worse than
   our own `sim.{scenario}.*` collision risk.** `group.status.<intersection>.
   <group_id>` and `detector.status.<id>` are built purely from the model
   conf's `topic_prefix` + id (`outputs.py`); there is no per-run or
   per-scenario qualifier at all. This is not hypothetical: the sumo_name
   `270_Tyyn_Vali` alone is reused across at least six different confs in
   this repo pointing at three different sumocfg files (`JS270_DEMO`,
   `FIELD_DEMO_1124`, two different `testmodel` variants). Any two OC
   engines using confs that share intersection numbering — routine across
   our dev/field/test confs — publish interleaved state on the same
   subjects today, with nothing to notice it. Their Option A (subscribe to
   our native subjects directly) inherits this as-is; it needs its own
   answer, independent of the scenario collision already logged for our
   `sim.*` interface (see `websumo_review_findings.md` #4).

2. **The model conf is not the geo join key it's described as.** §2.8 of
   their plan says the model file has "lanes (with coordinates!)". Checked
   against `models/JS270_DEMO/contr/JS270_DEMO.json` (a representative demo
   model): `signal_groups` holds only timing parameters (min/max green,
   etc.), `detectors` holds `type`/`sumo_id`/`channel`/`request_groups`,
   `group_list`/`group_outputs` are just ordered name lists. No coordinate
   or geometry data exists anywhere in an OC model conf. Any geographic
   join has to come from the net.xml (which is what our own
   `websumo_interface.py` already does for vehicles/persons via
   `convertGeo`), not from OC's config.

3. **Group → SUMO TLS-link mapping is implicit and positional, not a
   declarative table.** There is no group→link-index map to read
   statically. `PhaseRingController.get_sumo_states()`
   (`signal_group_controller.py`) builds the RYG string by concatenating
   each output group's state in the order given by `group_outputs` in the
   conf, matched positionally against SUMO's own `getControlledLinks()`
   order — and `group_outputs` can (and does) repeat a group's name
   consecutively when it controls more than one SUMO link. Reconstructing
   this join outside OC means replicating that positional logic exactly,
   not reading a field. If this project reaches Option B/C, the cleanest
   fix is OC publishing the already-resolved group→link mapping once
   (request-reply, same shape as our existing `.net`/`.detectors` serving)
   rather than WebSUMO re-deriving it.

None of this blocks their stated first slice (P1, Option A, one
intersection, zero OC changes) — it does mean their "the model file already
has the join, we just need to load it" framing needs correcting before
serious work starts, and it's the concrete argument for OC eventually
owning the join (Option C) rather than WebSUMO re-deriving OC's internal
positional logic.
