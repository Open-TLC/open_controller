# Traffic controller configuration

Configuring Open Controller, and more specifically the control engine, is done with a
YAML file. The file consists of configuration blocks that set options for different
aspects of the controller. One configuration file can have the settings for all
services of Open Controller (Simengine, Clockwork, and Traffic Indicators), or they can
be separated to their own files. All services share a set of
[general settings](#general-settings), that must be present in all configuration files.

The control engine of Open Controller (i.e. Clockwork), is the traffic controller
runner. It can be configured to run specific control logic internally, and send signal
states to either Simengine or the real ITC interface. On top of the general settings,
Clockwork service needs [control engine specific configurations](#control-engine-settings).

**Here is an example of a configuration file for Clockwork:**

```yaml
timer:
  timer_mode: fixed
  real_time_multiplier: 1
  time_step: 0.1

nats:
  url: nats
  port: 4222

clockwork:
  publisher:
    mode: change
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

detectors:
  - id: j1.0
    type: e1_detector
    options: {}
```

## General settings

General settings apply to all services of Open Controller, like Clockwork, Simengine,
and Traffic Indicators. They need to be shared across services to ensure synchronized
cooperation of components.

General settings include settings for **timer** and **NATS**, as they are used in all
services that operate in the same traffic scenario.

**Here is an example of general settings:**

```yaml
timer:
  timer_mode: real
  real_time_multiplier: 100
  time_step: 0.1

nats:
  url: nats
  port: 4222
```

### Timer settings

Running distributed systems in real time requires a timer to synchronize the actions
of all services. This timer is used mainly in Simengine and Clockwork to synchronize
the simulation and controller steps, so that control and simulation don't get out of
sync.

| Key | Type | Value | Comment |
| - | - | - | - |
| "timer_mode" | String | "fixed" / "real" | Fixed timer will run as fast as possible. Real timer will synchronize to the host machine clock. When running Open Controller with NATS, timer mode should be set to "real", which takes care of synchronizing different services. |
| "real_time_multiplier" | Float | 100 / 1 / 0.2 ... | When running in "real" mode, time can be accelerated or decelerated with this multiplier. When set to < 1, time will decelerate. When set to > 1, time will accelerate. When set to 1, timer will run in real time. |
| "time_step" | Float | 0.1 / 0.5 / 1 ... | Length of a single time step in seconds. |

### NATS settings

NATS is a server which provides communication services between various software
components based on publish and subscribe principle. To connect to a NATS server,
the client needs the address of the server, and the port number. URL should not include
"https://" prefix, as NATS uses its own protocol. The complete addresses look like this
`nats://some.url.com:4222`.

| Key | Type | Value | Comment |
| - | - | - | - |
| "url" | String | "10.8.0.36" / "localhost" / "nats.opencontroller.org" ... | The address of the NATS-server |
| "port" | Integer | 4222 / 8080 ... | Port number (default port of NATS is `4222`) |

## Control engine settings

Clockwork is responsible for both generating signal states, and publishing them to NATS for other services to consume. Thus also the configuration of Clockwork consists of settings fro [publisher](#publisher), and [ontrollers](#controllers).

```yaml
clockwork:
  publisher:
    mode: change
  controllers:
    - id: j1
      type: fixed_time
      options: {}
  detectors:
    - id: j1.0
      type: e2_detector
      options: {}
```

### Publisher

Publisher currently has only one setting, mode. This decides when are signal states published to NATS.

| Key | Type | Value | Comment |
| - | - | - | - |
| "mode" | String | "update" / "change" | Update will publish states on every update cycle. Change will only publish them when the states of a controller change. |

### Controllers

Controllers are the core of Clockwork. They represent control logic units for
intersections. Each controller controls a single intersection. As the configuration
needs of different control logics might differ, they have an arbitrary field "options",
that is meant to store logic specific options. All controllers need to have the
following three fields:

| Key | Type | Value | Comment |
| - | - | - | - |
| "id" | String | "j1" / "266" ... | Unique identifier of an intersection / controller. |
| "type" | String | "fixed_time" / "syvari" / "phase_ring" ... | Type of control logic. This is used to create the different controller units. |
| "options" | Dictionary | {"phases": [...]} | Control logic specific settings. Format depends on the type of controller. |

For more information about configuring different controllers, see
`services/control_engine/doc/controller_types/`.

### Detectors

Control engine can use detectors as data sources for the control logic. However,
detectors are not tied to just one controller, and thus, they are configured
separately. As with [controller](#controllers), detectors can also have different types
depending on the method of implementation. They also can have different configuring
needs, based on the type of detector they have. All detectors need to have the
following three fields:

| Key | Type | Value | Comment |
| - | - | - | - |
| "id" | String | "j1.0" / "266.0-001" ... | Unique identifier for the detector. Using the format `<intersection ID>.<detector ID>` is preferred, as it creates "namespaces". It also cleanly matches the NATS subjects of detectors. |
| "type" | String | "e1_detector" / "traffi_indicators" ... | Type of detector implementation. This is used to create the different detectors. |
| "options" | Dictionary | {"vehicle_types": [...]} | Detector type specific settings. Format depends on the type of detector. |
