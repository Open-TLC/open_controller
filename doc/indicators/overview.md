# Traffic Indicators Overview

## Purpose

The Traffic Indicators component is a core module of the Open Controller system that processes real-time traffic data from multiple sensors to generate high-level traffic insights. It consumes data from signal groups (traffic signals), loop detectors, and radar sensors, then calculates macro and micro traffic indicators to support intelligent traffic control decisions.

## Scope

This component:
- Reads sensor data from NATS messaging channels in JSON format
- Processes signal group status, detector events, and radar object tracking
- Generates traffic indicators (vehicle counts, speeds, densities) per signal group
- Outputs processed data via NATS for consumption by traffic controllers
- Supports both simulated (SUMO) and real-world sensor data
- Can run as part of Open Controller or standalone

## Architecture Summary

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Data Sources  │───▶│ Traffic Indicators│───▶│    Outputs      │
│                 │    │                  │    │                 │
│ • Signal Groups │    │ ┌──────────────┐ │    │ • Vehicle Counts│
│ • Loop Detectors│    │ │ Sensor Twin  │ │    │ • Speed Data    │
│ • Radar Sensors │    │ │              │ │    │ • Traffic Views │
│                 │    │ └──────────────┘ │    │                 │
│                 │    │ ┌──────────────┐ │    │                 │
│                 │    │ │ Field of View│ │    │                 │
│                 │    │ │ Processing   │ │    │                 │
│                 │    │ └──────────────┘ │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
       NATS                   Component                NATS
```

### Key Components

- **SensorTwin**: Main orchestrator that manages sensor objects and data flow
- **Radar**: Processes radar object tracking data from traffic sensors
- **Detector**: Handles loop detector activation events
- **Group**: Manages traffic signal group status information
- **FieldOfView**: Combines multiple sensor inputs to generate traffic views
- **GlobalConf**: Configuration management for sensors, connections, and outputs

### Data Flow

1. Component subscribes to NATS topics for sensor data streams
2. Incoming data is routed to appropriate sensor objects (Radar, Detector, Group)
3. Sensor objects store and process historical data
4. FieldOfView objects aggregate data from multiple sensors
5. Traffic indicators are calculated and published to output NATS topics
6. Background tasks handle data cleanup and periodic processing

### Integration

- **Input**: NATS messaging for real-time sensor data
- **Output**: NATS messaging for processed traffic indicators
- **Configuration**: JSON-based configuration files
- **Deployment**: Docker containerized or standalone Python execution
- **Dependencies**: Python 3.9+, NATS client library, jsmin for config parsing

## Related Documentation

- [Inputs and Outputs](inputs_outputs.md) - Detailed data schemas and examples
- [Configuration](configuration.md) - Configuration file structure and options
- [Installation and Running](install_and_run.md) - Setup and execution instructions
- [Troubleshooting](troubleshooting.md) - Common issues and diagnostics
