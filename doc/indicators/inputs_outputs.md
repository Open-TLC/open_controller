# Inputs and Outputs

The Traffic Indicators component processes three types of input data and generates traffic view outputs via NATS messaging.

## Input Data Sources

### 1. Signal Group Status

**Transport**: NATS messaging
**Topic Pattern**: `group.status.270.*`
**Source**: Traffic signal controllers or SUMO simulation
**Frequency**: On state change events

**Schema**:
```json
{
  "id": "string",        // Signal group identifier (e.g., "group.status.270.7")
  "tstamp": "string",    // ISO timestamp (e.g., "2025-12-02T13:44:58.998153")
  "substate": "string"   // Signal state: "g" (green), "r" (red), "y" (yellow)
}
```

**Example Payloads**:
```json
{"id": "group.status.270.7", "tstamp": "2025-12-02T13:44:58.998153", "substate": "g"}
{"id": "group.status.270.5", "tstamp": "2025-12-02T13:45:15.398824", "substate": "r"}
```

**Required Fields**: id, tstamp, substate
**Validation**: substate must be one of "g", "r", "y"
**Error Handling**: Invalid substates are logged and ignored

### 2. Loop Detector Events

**Transport**: NATS messaging
**Topic Pattern**: `detector.status.*`
**Source**: Loop detectors or SUMO simulation
**Frequency**: On detector state changes (vehicle presence)

**Schema**:
```json
{
  "id": "string",        // Detector identifier (e.g., "detector.status.6-002A")
  "loop_on": "boolean",  // true when vehicle detected, false when clear
  "tstamp": "string"     // ISO timestamp
}
```

**Example Payloads**:
```json
{"id": "detector.status.6-002A", "loop_on": true, "tstamp": "2025-12-02T13:46:17.304341"}
{"id": "detector.status.5-040", "loop_on": false, "tstamp": "2025-12-02T13:46:20.409100"}
```

**Required Fields**: id, loop_on, tstamp
**Validation**: loop_on must be boolean
**Error Handling**: Malformed detector events are logged and discarded

### 3. Radar Object Tracking

**Transport**: NATS messaging
**Topic Pattern**: `radar.270.*.objects_port.json`
**Source**: Radar sensors or SUMO simulation
**Frequency**: Periodic updates (typically 10Hz)

**Schema**:
```json
{
  "source": "string",      // Data source ("sumo" or radar identifier)
  "status": "string",      // "OK" or error status
  "tstamp": "number",      // Unix timestamp in milliseconds
  "nobjects": "number",    // Number of tracked objects
  "objects": [             // Array of tracked objects
    {
      "id": "number",           // Unique object ID
      "lat": "number",          // Latitude coordinate
      "lon": "number",          // Longitude coordinate
      "speed": "number",        // Speed in m/s
      "acceleration": "number", // Acceleration in m/s²
      "len": "number",          // Object length in meters
      "lane": "number",         // Lane identifier
      "class": "mixed",         // Vehicle class (number or string)
      "quality": "number",      // Detection quality (0-100)
      "sumo_id": "string",      // SUMO-specific vehicle ID
      "sumo_type": "string",    // SUMO-specific vehicle type
      "sumo_angle": "number",   // SUMO-specific angle
      "sumo_class": "string",   // SUMO-specific class
      "cyc_ago": "number"       // Cycles since last detection
    }
  ]
}
```

**Example Payload** (abbreviated):
```json
{
  "source": "sumo", 
  "status": "OK", 
  "tstamp": 1764683294201, 
  "nobjects": 2,
  "objects": [
    {
      "id": 60, "lat": 60.160324, "lon": 24.922073, "speed": 5.62, 
      "acceleration": 0.59, "len": 1.6, "lane": -1, "class": "bike", 
      "quality": 100, "sumo_id": "F_Jatk2Vali_bike.4"
    }
  ]
}
```

**Required Fields**: source, status, tstamp, nobjects, objects
**Object Required Fields**: id, lat, lon, speed, class
**Validation**: Coordinates must be valid, speed >= 0, quality 0-100
**Error Handling**: Invalid objects are filtered out, malformed messages logged

## Output Data

### Traffic View Indicators

**Transport**: NATS messaging
**Topic Pattern**: `group.e3.270.*`
**Frequency**: Every second
**Consumers**: Open Controller clockwork component, external systems

**Schema**:
```json
{
  "count": "number",           // Total vehicle count in view
  "radar_count": "number",     // Count from radar sensors
  "det_vehcount": "number",    // Count from loop detectors
  "group_substate": "string",  // Current signal group state
  "view_name": "string",       // Identifier for this traffic view
  "objects": {},               // Object details keyed by object ID
  "offsets": {},               // Lane offset corrections
  "tstamp": "number"           // Unix timestamp with microseconds
}
```

**Objects Sub-schema**:
```json
{
  "object_id": {
    "speed": "number",      // Object speed in m/s
    "quality": "number",    // Detection quality (0-100)
    "sumo_id": "string",    // Original SUMO identifier
    "vtype": "string"       // Vehicle type classification
  }
}
```

**Offsets Sub-schema**:
```json
{
  "Lane_Name": "number"    // Offset correction value for lane
}
```

**Example Outputs**:
```json
// Active traffic view
{
  "count": 1, "radar_count": 1, "det_vehcount": 1, 
  "group_substate": "r", "view_name": "group5_view",
  "objects": {
    "92": {"speed": 8.85, "quality": 100, "sumo_id": "F_Jatk2Sat.30", "vtype": "car_type"}
  },
  "offsets": {"Group 5 lane 1": 0}, "tstamp": 1764683431446.249
}

// Empty traffic view
{
  "count": 0, "radar_count": 0, "det_vehcount": 0,
  "group_substate": "r", "view_name": "group4_view",
  "objects": {}, "offsets": {"Group 4 lane 1": 0}, "tstamp": 1764683431446.171
}
```

**Required Fields**: count, radar_count, det_vehcount, group_substate, view_name, tstamp
**Validation**: Counts must be non-negative integers, tstamp must be valid
**Error Handling**: Failed outputs are logged, component continues operation

## Data Processing Rules

### Vehicle Classification

Radar class codes are mapped to SUMO vehicle types:
- 0, 3, 4, 5, 6 → "car_type"
- 1, 2 → "bike_type" 
- 7 → "truck_type"
- 8 → "tram_type"

### Quality Filtering

Objects with quality < configurable threshold (default 50) are excluded from processing.

### Temporal Aggregation

Detector counts use sliding windows, radar data uses recent measurements (default 1 second history).

### Error Recovery

- Network disconnections trigger automatic reconnection
- Malformed JSON messages are logged and skipped
- Missing sensor data is handled gracefully with zero counts
- Stale data is automatically cleaned up via background tasks
