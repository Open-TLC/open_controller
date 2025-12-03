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

### Docker Compose (recommended)
Use the repo’s Docker setup so the `indicators` service can reach the `nats` service via the Docker network hostname `nats` (as expected by `run_indicators.sh`).
```bash
# In the open controller directory
docker-compose up nats indicators
```
- Entrypoint: `docker/indicators/run_indicators.sh` (runs Python with `--nats-server nats`)
- Requirements: `docker/indicators/requirements.txt`

### Standalone (Python)
```bash
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
  - Listen to input streams with NATS CLI (for the testmodel):
    ```bash
    # Signal group states (e.g., junction 270)
    nats sub "group.status.270.*"

    # Loop detector events
    nats sub "detector.status.*"

    # Radar objects (all radars under junction 270)
    nats sub "radar.270.*.objects_port.json"
    ```
- No outputs:
  - Confirm `outputs` are configured and `trigger_time` > 0.
  - Ensure lanes and groups referenced by views exist.
  - Listen to indicator outputs:
    ```bash
    # E3 traffic views for junction 270
    nats sub "group.e3.270.*"
    ```


## Links to Further Documentation
- Configuration: to be authored in `doc/indicators/configuration.md`
- Inputs/Outputs: to be authored in `doc/indicators/inputs_outputs.md`
- Troubleshooting: to be authored in `doc/indicators/troubleshooting.md`
- Milestone summary: `doc/indicators/milestone_summary.md`

