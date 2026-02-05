# Inputs and Outputs

This document summarizes the Traffic Indicators component’s inputs and outputs at a practical, high level, with the essential subjects, field shapes, and small samples to help integration and troubleshooting.

## Inputs (High-Level)

- Transport: NATS (local or remote server)
- Sources: Simulation (SUMO) or real devices/controllers
- Format: JSON messages with timestamps; some SUMO-specific fields may be present but are not always used.

### 1) Signal Group Status
- Purpose: Current state of each signal group; drives phase-aware logic (counter resets/blocks).
- Subject pattern: `group.status.270.*` → e.g., `group.status.270.7`
- Minimal shape:
```json
{
  "id": "group.status.270.7",
  "tstamp": "2025-12-02T13:44:58.998153",
  "substate": "g"  // examples include "g", "r"; also other phase codes
}
```

- Field reference

| Key | Description | Required | Example | Type |
|---|---|---|---|---|
| `id` | Fully qualified group subject for the event | Yes | `group.status.270.7` | string |
| `tstamp` | ISO 8601 timestamp when the state applied | Yes | `2025-12-02T13:44:58.998153` | string (ISO8601) |
| `substate` | Signal substate code (e.g., red/green phases) | Yes | `g` | string |
- Notes:
  - Timestamp is ISO 8601
  - Substate codes are used to reset or block detector-derived counts

### 2) Loop Detector Events
- Purpose: Presence edges for estimating lane vehicle counts.
- Subject pattern: `detector.status.*` → e.g., `detector.status.5-040`
- Minimal shape:
```json
{
  "id": "detector.status.6-002A",
  "loop_on": true,
  "tstamp": "2025-12-02T13:46:17.304341"
}
```

- Field reference

| Key | Description | Required | Example | Type |
|---|---|---|---|---|
| `id` | Fully qualified detector subject for the event | Yes | `detector.status.6-002A` | string |
| `loop_on` | Detector presence (true on, false off) | Yes | `true` | boolean |
| `tstamp` | ISO 8601 timestamp when the sample was generated | Yes | `2025-12-02T13:46:17.304341` | string (ISO8601) |
- Notes:
  - `loop_on` toggles, and the configured edge (`rising_edge`/`falling_edge`) determines counting
  - Timestamp is ISO 8601

### 3) Radar Object Streams
- Purpose: Object-level detection per lane (used for micro indicators and counts).
- Subject patterns: `radar.270.<n>.objects_port.json` → e.g., `radar.270.1.objects_port.json`
- Minimal envelope:
```json
{
  "source": "sumo",
  "status": "OK",
  "tstamp": 1764683294201,  // ms epoch
  "nobjects": 4,
  "objects": [
    {
      "id": 60,
      "lat": 60.1603245,
      "lon": 24.9220732,
      "speed": 5.62,
      "acceleration": 0.59,
      "len": 1.6,
      "lane": -1,
      "class": "bike",
      "quality": 100,
      "sumo_id": "F_Jatk2Vali_bike.4"
    }
  ]
}
```

- Field reference (envelope)

| Key | Description | Required | Example | Type |
|---|---|---|---|---|
| `source` | Source identifier (e.g., `sumo` or device id) | Yes | `sumo` | string |
| `status` | Feed status | Yes | `OK` | string |
| `tstamp` | Sample timestamp in milliseconds since epoch | Yes | `1764683294201` | number (ms epoch) |
| `nobjects` | Number of objects in this message | Yes | `4` | number |
| `objects` | Array of tracked objects | Yes | `[ {...} ]` | array of Object |

- Field reference (object item)

| Key | Description | Required | Example | Type |
|---|---|---|---|---|
| `id` | Unique object id within stream | Yes | `60` | number |
| `lat` | Latitude | Yes | `60.1603245` | number |
| `lon` | Longitude | Yes | `24.9220732` | number |
| `speed` | Speed | Yes | `5.62` | number (m/s) |
| `acceleration` | Acceleration | No | `0.59` | number (m/s²) |
| `len` | Object length | No | `1.6` | number (m) |
| `lane` | Lane index at sensor | Yes | `-1` | number |
| `class` | Raw class from sensor/simulator | Yes | `bike` | string/number |
| `quality` | Detection quality (0–100) | No | `100` | number |
| `sumo_id` | Simulator vehicle id (if SUMO) | No | `F_Jatk2Vali_bike.4` | string |
| `sumo_type` | Simulator type (if SUMO) | No | `bike` | string |
| `sumo_angle` | Simulator angle (if SUMO) | No | `221.46` | number |
| `sumo_class` | Simulator class (if SUMO) | No | `bike` | string |
| `cyc_ago` | Cycles since last seen | No | `0` | number |

See also (radar payload semantics and updates):
https://bitbucket.org/conveqs/conveqs_platform_interface/src/master/
- Notes:
  - Timestamp is epoch milliseconds
  - Only a subset of fields is used downstream (lane, speed, quality, class/type)

## Outputs (High-Level)

- Transport: NATS (published periodically)
- Consumers: Open Controller (clockwork), external clients/tools
- Frequency: Configurable (typical: 1 second)

### E3 Traffic View
- Purpose: Per–signal-group fused indicator set (macro + micro)
- Subject pattern: `group.e3.270.*` → e.g., `group.e3.270.5`
- Minimal shape:
```json
{
  "count": 1,               // combined objects count
  "radar_count": 1,         // objects from radar
  "det_vehcount": 1,        // detector-derived vehicle count
  "group_substate": "r",   // current signal state
  "view_name": "group5_view",
  "objects": {
    "92": {"speed": 8.85, "quality": 100, "sumo_id": "F_Jatk2Sat.30", "vtype": "car_type"}
  },
  "offsets": {"Group 5 lane 1": 0},
  "tstamp": 1764683431446.249
}
```

- Field reference (envelope)

| Key | Description | Required | Example | Type |
|---|---|---|---|---|
| `count` | Total number of combined objects | Yes | `1` | number |
| `radar_count` | Number of radar-derived objects | Yes | `1` | number |
| `det_vehcount` | Detector-based vehicle count (with offsets) | Yes | `1` | number |
| `group_substate` | Current signal substate | Yes | `r` | string |
| `view_name` | Output view name from config | Yes | `group5_view` | string |
| `objects` | Map of object details keyed by object id | Yes | `{ "92": {...} }` | object (map) |
| `offsets` | Map of lane offsets used in detector drift correction | Yes | `{ "Group 5 lane 1": 0 }` | object (map) |
| `tstamp` | Output timestamp in milliseconds since epoch (float) | Yes | `1764683431446.249` | number |

- Field reference (objects map value)

| Key | Description | Required | Example | Type |
|---|---|---|---|---|
| `speed` | Object speed | Yes | `8.85` | number (m/s) |
| `quality` | Detection quality (0–100) | No | `100` | number |
| `sumo_id` | Simulator id when available | No | `F_Jatk2Sat.30` | string |
| `vtype` | Normalized vehicle type (e.g., car_type, truck_type) | Yes | `car_type` | string |
- Notes:
  - `objects` include only reliably classified types (e.g., cars/trucks) for micro indicators
  - `offsets` represent per-lane detector drift correction

## Validation & Error Handling (Practical)

- JSON parsing errors: ignored/logged; processing continues
- Missing fields: best-effort processing with sensible defaults or filtering
- Stale data: old entries cleaned on intervals; outputs reflect freshest available inputs
- Negative detector counts: offsets reset to guard against drift; processing continues

## Quick Monitoring (NATS CLI)

```bash
# Inputs
nats sub "group.status.270.*"
nats sub "detector.status.*"
nats sub "radar.270.*.objects_port.json"

# Outputs
nats sub "group.e3.270.*"
```

## References
- Config: `models/testmodel/indicators.json`
- Code: `src/indicators/*.py` (`traffic_indicators.py`, `confread.py`, `radar.py`, `detector.py`, `group.py`, `fusion.py`)
- Samples: `tmp/indicators_data_stream.txt.md`
