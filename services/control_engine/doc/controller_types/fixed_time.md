# Fixed time controller

The fixed time controller (`type: fixed_time`,
`src/fixed_time_controller/controller.py`) is the simplest controller type:
it rotates through a list of pre-configured phases with fixed durations,
paying no attention to detectors or traffic. It is not a real production
controller - it exists for testing and demonstration, and can be thought of
as the Hello World of Open Controller.

## Operation

The controller is configured with a list of phases, each a SUMO-style signal
state string (one character per signal link: `g` green, `r` red) and a
duration in seconds. After each configured phase the controller
automatically inserts a yellow transition phase: the phase's `g` characters
are replaced with `y`, shown for the common `yellow_duration`. The
controller then advances to the next configured phase, wrapping around at
the end of the list.

On every tick the controller checks whether the current phase (or inserted
yellow phase) has run its duration, and moves to the next one when it has.
There are no requests, extensions or intergreen calculations - purely a
clock.

## Configuration

Under a controller entry in the `clockwork.controllers` list:

```yaml
clockwork:
  controllers:
    - id: j1
      type: fixed_time
      options:
        phases:
          - signal_states: ggrrrr
            duration: 10
          - signal_states: rrggrr
            duration: 10
          - signal_states: rrrrgg
            duration: 10
        yellow_duration: 3
```

| Option | Description |
|---|---|
| `phases` | List of phases, rotated in order. Each has `signal_states` (SUMO state string, one character per signal link of the intersection) and `duration` (seconds). |
| `yellow_duration` | Duration (seconds) of the automatically inserted yellow phase after each configured phase. |

The `signal_states` strings must have one character per signal link of the
SUMO traffic light the controller drives (the controller `id` has to match
the SUMO object), in SUMO's link indexing order.

See the [configuration reference](../configuration.md) for the general
settings shared by all controller types.
