# Signal group operation

Each signal group (`SignalGroup`) is implemented as a state machine. That top-level
state machine has four states - Red, AmberRed, Green and Amber - and each of these
states is itself a nested state machine (a "substate machine") that governs what
happens while the signal group is in that phase.

```
Red -> AmberRed -> Green -> Amber -> Red -> ...
```

## Creating the state diagrams

The diagrams in this document are generated directly from the `transitions`-based
state machine implementation in `signal_group.py`, so they always reflect the
actual code rather than a hand-drawn approximation of it.

From the repository root, with a YAML controller configuration (e.g. one of the
files under `models/`, or your own):

```
mkdir -p tmp

# Full ring: all four phases in one diagram
uv run python -m services.control_engine.src.signal_group --conf-file models/test/simple/contr.yaml

# One diagram per phase (Red, AmberRed, Green, Amber)
uv run python -m services.control_engine.src.signal_group --submachines --conf-file models/test/simple/contr.yaml
```

Generating the diagrams needs the `graphviz` system package (the `dot`
command) in addition to the Python dependencies.

The full ring is written to `tmp/ring.png`, and the per-phase diagrams to
`tmp/ring_red.png`, `tmp/ring_amber_red.png`, `tmp/ring_green.png` and
`tmp/ring_amber.png`. It always diagrams one signal group of the first
controller listed under `clockwork.controllers` in the given configuration
file.

Where an arrow's guard is implemented as a named condition method, the label
shows its name (e.g. `_min_time_passed`); guards implemented as inline
lambdas show as `<lambda>` on the diagram - the sections below spell out what
each of those conditions is.

## Operation

### Full ring

![Full signal group ring](figures/full_signalgroup_ring.png)

The signal group cycles through Red, AmberRed, Green and Amber in a fixed order -
there is no other possible sequence. Every transition is a `next_state`
transition, fired on every controller tick; a transition happens when its
guard conditions are true. Each of the four phases is its own nested state
machine: AmberRed and Amber are plain fixed-time phases (`FixedTime`), Red
adds the group-based green-start logic (`GroupBasedRed`), and Green adds the
extension logic (`ExtendedGreen`).

### AmberRed

![AmberRed substate machine](figures/signalgroup_ring_amber_red.png)

AmberRed is one of the simple phases: it starts in `MinimumTime`, which runs
a minimum time that, in this phase, is also its maximum time (`min_amber_red`
in the configuration). `MinimumTime` moves to `Exit` once `_min_time_passed`
becomes true, ending the phase.

### Amber

![Amber substate machine](figures/signalgroup_ring_amber.png)

Amber works the same way as AmberRed: `MinimumTime` moves to `Exit` once
`_min_time_passed` is true - again, minimum time and maximum time are the
same here (`min_amber`).

### Red

![Red substate machine](figures/signalgroup_ring_red.png)

Red (`GroupBasedRed`) is more complex than the two fixed-time phases:

- `MinimumTime` moves to `WaitRequestAndPermission` once `_min_time_passed`
  is true (`min_red`). Entering `WaitRequestAndPermission` also clears any
  leftover end-green request on the group.
- `WaitRequestAndPermission` moves to `EndingConflicts` once the group both
  has a green request (`is_requesting`) and the controller has given it
  permission to go green (`green_permission`).
- On entering `EndingConflicts` the group requests all of its conflicting
  groups to end their greens (`end_conflict_greens()`). It moves on to
  `WaitIntergreen` once no conflicting group is blocking anymore
  (`conflict_group_blocking()` is false), meaning the conflicts have left
  their Green/Amber states.
- `WaitIntergreen` waits for the intergreen times towards the conflicting
  groups to pass; it moves to `Exit`, ending the Red phase, once
  `_intergreens_passed` is true. From this point on the transition to green
  can no longer be blocked.

### Green

![Green substate machine](figures/signalgroup_ring_green.png)

Green (`ExtendedGreen`) starts the same way as the other phases, but what
happens after the minimum time depends on the group's extenders and the
`remain_green` configuration setting:

- `MinimumTime` moves to `Extending` once `_min_time_passed` is true
  (`min_green`). Every green phase always passes through `Extending`.
- From `Extending`, what happens next depends on `remain_green`:
  - With `remain_green: false`, green ends when the extenders stop extending
    (`is_extending` becomes false) or when the maximum green time is reached
    (`_max_time_passed`, `max_green`) - both move straight to `Exit`.
  - With `remain_green: true`, the same two conditions move to `RemainGreen`
    instead: the group keeps a passive green after its extensions end.
- `RemainGreen` moves to `Exit` once a conflicting group requests this group
  to end its green (`end_green_requested`, set by the conflicting group's
  `end_conflict_greens()` when it starts its own green process) - in
  practice, the group stays green until someone else needs the right of way.

## Interfaces

Signal groups generally operate independently of each other, and change
state automatically within `tick()` (`SignalGroup.tick()`,
`signal_group.py`): every tick first updates the group's requesters and
extenders, then calls `next_state()`, which fires whichever `next_state`
transition (if any) has its guard conditions currently true.

Some of the conditions are purely clock-driven, such as `_min_time_passed`
and `_intergreens_passed` above. The others depend on objects attached to
the group from the outside:

- **Requesters** (`requesters/`) decide whether there is demand for green
  time. The group's `is_requesting` property is true if any of its
  requesters is requesting - or always, if the group is configured with
  `constant_request`. Current requester types are the presence requester
  (demand while a detector is occupied) and the trigger requester (demand
  latched by a detector pulse until served). This feeds the
  `WaitRequestAndPermission -> EndingConflicts` transition in Red.
- **Extenders** (`extenders/`) decide whether the active green should
  continue. The group's `is_extending` property is true if any of its
  extenders is extending. Current extender types are the gap-seeking
  extender (extends while vehicles keep arriving within the gap time) and
  the smart extender. This feeds the `Extending` transitions in Green.
- **Permission to go green** (`green_permission`) - whether the controller
  allows this group to start green if it has a request. This coordinates
  the order in which groups go green when several of them want to at the
  same time: the phase ring controller
  (`signal_group_controller.py`) grants and revokes it per main phase.
- **End-green request** (`end_green_requested`) - set on this group by a
  conflicting group that is starting its own green process; it ends this
  group's `RemainGreen` state.
