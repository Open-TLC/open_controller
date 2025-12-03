# Traffic Indicators

## Overview

The Traffic Indicators component reads real-time inputs from signal groups (traffic signals), loop detectors, and radarsin JSON over NATS. The source of these inputs can be either traffic simulator (see simengine component for more details) or real data sources in the field.

It fuses these inputs into high-level "views" (traffic indicators), one for signal group. These indicators include macro signals (total vehicles, counts by source, current signal state) and micro signals (selected object details such as speed, quality, and type) to support controller signal timing. The component can run standalone or as part of the Open Controller stack.

In practice, the service:
- Ingests sensor data via NATS (signal groups, loop detectors, radars).
- Maintains in-memory sensor state and fuses inputs per approach using Field of View definitions.
- Publishes periodic indicators (macro and micro) to NATS for downstream consumption by the controller and external systems.

The component is intended to be expanded to use more inputs and perform several data fusion functionalitieds

## Quick Install and Run

### Docker (recommended)
```bash
# Build image
docker build -f docker/indicators/Dockerfile -t traffic-indicators .
# Run with host networking to reach local NATS
docker run -it --name indicators --network host traffic-indicators
```
- Entry script: `docker/indicators/run_indicators.sh`
- Requirements: `docker/indicators/requirements.txt`

### Standalone (Python)
```bash
cd /Users/karikoskinen/Documents/work/conveqs/dev/source/open_controller
pip install -r docker/indicators/requirements.txt
python src/indicators/traffic_indicators.py --conf models/testmodel/indicators.json --nats-server localhost
```

### Command Line Parameters
```bash
python src/indicators/traffic_indicators.py [OPTIONS]
  --version                 Show version
  --conf CONFIG_FILE        Path to configuration JSON
  --nats-server SERVER      NATS server address (default: localhost)
  --nats-port PORT          NATS server port (default: 4222)
```

## Common Issues
- No NATS connectivity:
  - Ensure NATS is running and reachable (`localhost:4222` by default).
  - In Docker Compose, use the service host (e.g., `nats`).
- No input data:
  - Verify simulation/devices publish to expected subjects.
  - Check configuration paths and subject patterns.
- No outputs:
  - Confirm `outputs` are configured and `trigger_time` > 0.
  - Ensure lanes and groups referenced by views exist.

## Links to Further Documentation
- Configuration: to be authored in `doc/indicators/configuration.md`
- Inputs/Outputs: to be authored in `doc/indicators/inputs_outputs.md`
- Troubleshooting: to be authored in `doc/indicators/troubleshooting.md`
- Milestone summary: `doc/indicators/milestone_summary.md`

## Short Overview Summary
This component reads data inputs from given channels — namely signal group (traffic signal) statuses, loop detectors, and radars — from simulated or real sources in JSON format. It then calculates high-level “views” or traffic indicators from them. These indicators are used by the traffic controller for signal timings. Outputs are generally one per signal group and consist of macro and micro indicators of the amount of traffic.

The component is intended to be used as part of Open Controller, but it can be run standalone as well.
