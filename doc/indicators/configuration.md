# Configuration

The Traffic Indicators component uses JSON-based configuration to define data sources, processing parameters, and output destinations.

## Configuration File Structure

Default configuration location: `models/testmodel/indicators.json`

### Main Configuration Sections

```json
{
  "connectivity": {},      // NATS and other connection parameters
  "input_streams": {},     // Data source definitions
  "outputs": {}            // Output stream configurations
}
```

## Connectivity Configuration

**Purpose**: Define connection parameters for NATS messaging and other services.

```json
"connectivity": {
  "notes": "This is for accessing the data",
  "nats": {
    "server": "localhost",
    "port": 4222
  },
  "hsl": {
    "server": "to be defined",
    "port": 8080
  }
}
```

**Parameters**:
- `nats.server` (string): NATS server hostname or IP address
- `nats.port` (integer): NATS server port number
- `hsl` (object): Reserved for future HSL API integration

**Defaults**:
- NATS server: "localhost"
- NATS port: 4222

## Input Streams Configuration

**Purpose**: Define data sources and their NATS subscription patterns.

### Signal Group Inputs

```json
"sig_inputs": {
  "connection": "nats",
  "type": "groups",
  "subtype": "sumo",
  "nats_subject": "group.status.270.*",
  "notes": "Will subscribe to all groups sent by sumo"
}
```

### Detector Inputs

```json
"det_inputs": {
  "connection": "nats",
  "type": "detectors",
  "subtype": "sumo",
  "nats_subject": "detector.status.*",
  "notes": "Will subscribe to all detectors sent by sumo"
}
```

### Radar Inputs

```json
"radar270.1": {
  "connection": "nats",
  "type": "radar",
  "subtype": "sumo",
  "nats_subject": "radar.270.1.objects_port.json",
  "notes": "Will subscribe to radar pointing north"
}
```

**Input Stream Parameters**:
- `connection` (string): Connection type (currently only "nats")
- `type` (string): Data type ("groups", "detectors", "radar")
- `subtype` (string): Data source subtype ("sumo", "real")
- `nats_subject` (string): NATS topic subscription pattern
- `notes` (string): Human-readable description

## Output Configuration

Outputs are configured in the `outputs` section and define field-of-view processing zones.

### Field of View Configuration

```json
"outputs": {
  "group2_view": {
    "type": "e3",
    "nats_output_subj": "group.e3.270.2",
    "group": "group270.2",
    "lanes": {
      "Group 2 lane 1": {
        "name": "Group 2 lane 1",
        "lane_main_type": "car_type",
        "radar_lanes": {
          "radar270.1_lane1": {"stream": "radar270.1", "lane": 1}
        },
        "in_dets": {"detector.status.2-001": {}},
        "out_dets": {"detector.status.2-002": {}}
      }
    }
  }
}
```

**Output Parameters**:
- `type` (string): Output type ("e3" for traffic view)
- `nats_output_subj` (string): NATS topic for publishing results
- `group` (string): Associated signal group identifier
- `lanes` (object): Lane-specific processing configuration

**Lane Parameters**:
- `name` (string): Human-readable lane identifier
- `lane_main_type` (string): Primary vehicle type for this lane
- `radar_lanes` (object): Radar data sources for this lane
- `in_dets` (object): Inbound detector identifiers
- `out_dets` (object): Outbound detector identifiers

## Environment Variables

The component supports environment variable overrides:

- `NATS_SERVER`: Override NATS server address
- `NATS_PORT`: Override NATS server port

## Command Line Configuration

Command line arguments override both file and environment settings:

```bash
--conf CONFIG_FILE          # Path to configuration JSON file
--nats-server SERVER_ADDR    # NATS server address
--nats-port PORT_NUMBER      # NATS server port
```

## Configuration Loading Priority

1. **Default values**: Built-in defaults from `confread.py`
2. **Configuration file**: JSON file specified via `--conf` parameter
3. **Environment variables**: OS environment variable overrides
4. **Command line**: Command line argument overrides

Each level overrides the previous one for any parameters that are specified.

## Configuration Validation

### Required Fields
- At least one input stream must be defined
- NATS connectivity parameters must be valid
- Output streams must reference valid input streams

### Default Values

From `src/indicators/confread.py`:
```python
DEFAULT_NATS_SERVER = "localhost"
DEFAULT_NATS_PORT = 4222
DEFAULT_SUBJECT_STAT_DETECTORS = "detector.status"
DEFAULT_SUBJECT_STAT_GROUPS = "group.status"
```

### Error Handling

- **File not found**: Component logs error and uses default values
- **Invalid JSON**: Component exits with parsing error
- **Missing required fields**: Component logs warnings and uses defaults
- **Invalid data types**: Component logs warnings and skips invalid entries

## Example Complete Configuration

```json
{
  "connectivity": {
    "nats": {
      "server": "localhost",
      "port": 4222
    }
  },
  "input_streams": {
    "sig_inputs": {
      "connection": "nats",
      "type": "groups",
      "nats_subject": "group.status.270.*"
    },
    "det_inputs": {
      "connection": "nats",
      "type": "detectors",
      "nats_subject": "detector.status.*"
    },
    "radar270.1": {
      "connection": "nats",
      "type": "radar",
      "nats_subject": "radar.270.1.objects_port.json"
    }
  },
  "outputs": {
    "group5_view": {
      "type": "e3",
      "nats_output_subj": "group.e3.270.5",
      "group": "group270.5",
      "lanes": {
        "Group 5 lane 1": {
          "name": "Group 5 lane 1",
          "radar_lanes": {
            "radar270.1_lane1": {"stream": "radar270.1", "lane": 1}
          },
          "in_dets": {"detector.status.5-002": {}},
          "out_dets": {"detector.status.5-040": {}}
        }
      }
    }
  }
}
```

## Configuration Testing

To validate configuration:
```bash
python -c "from confread import GlobalConf; print(GlobalConf(conf='your_config.json').get_json_str(prettyprint=True))"
```
