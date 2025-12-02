# Installation and Running

The Traffic Indicators component can be run using Docker (recommended) or as a standalone Python application.

## Prerequisites

### Required Software
- Docker and Docker Compose (for containerized deployment)
- Python 3.9+ (for standalone deployment)
- NATS Server (running locally or remotely)

### System Requirements
- Linux, macOS, or Windows
- Minimum 512MB RAM
- Network access to NATS server
- Access to sensor data sources

## Docker Deployment (Recommended)

### Quick Start

1. **Navigate to project root**:
   ```bash
   cd /path/to/open_controller
   ```

2. **Build and run with Docker Compose**:
   ```bash
   docker-compose up indicators
   ```

### Manual Docker Build

1. **Build the Docker image**:
   ```bash
   docker build -f docker/indicators/Dockerfile -t traffic-indicators .
   ```

2. **Run the container**:
   ```bash
   docker run -it --name indicators \
     --network host \
     traffic-indicators
   ```

### Docker Configuration

**Dockerfile location**: `docker/indicators/Dockerfile`
**Base image**: `python:3.9-slim`
**Working directory**: `/app`

**Environment variables**:
```bash
# Override NATS server connection
docker run -e NATS_SERVER=remote-nats-server \
           -e NATS_PORT=4222 \
           traffic-indicators
```

**Volume mounts for custom configuration**:
```bash
docker run -v /path/to/custom/indicators.json:/app/models/testmodel/indicators.json \
           traffic-indicators
```

## Standalone Python Deployment

### Installation Steps

1. **Clone repository**:
   ```bash
   git clone <repository-url>
   cd open_controller
   ```

2. **Install Python dependencies**:
   ```bash
   pip install -r docker/indicators/requirements.txt
   ```

   Required packages:
   - `jsmin==3.0.1` (JSON minification)
   - `nats-py==2.9.0` (NATS client library)

3. **Install NATS Server** (if running locally):
   
   **macOS**:
   ```bash
   brew install nats-server
   nats-server
   ```
   
   **Linux (Ubuntu/Debian)**:
   ```bash
   curl -sf https://binaries.nats.dev/nats-io/nats-server/v2@latest | sh
   sudo mv nats-server /usr/local/bin/
   nats-server
   ```
   
   **Docker NATS**:
   ```bash
   docker run -p 4222:4222 nats:latest
   ```

### Running the Component

**Basic execution**:
```bash
cd /path/to/open_controller
python src/indicators/traffic_indicators.py
```

**With configuration file**:
```bash
python src/indicators/traffic_indicators.py --conf models/testmodel/indicators.json
```

**With custom NATS server**:
```bash
python src/indicators/traffic_indicators.py \
  --conf models/testmodel/indicators.json \
  --nats-server 192.168.1.100 \
  --nats-port 4222
```

## Command Line Parameters

```
Usage: traffic_indicators.py [OPTIONS]

Runs the sumo in real time and relays the detector and group states to a nats-server

Optional arguments:
  --version              Show version information
  --conf CONFIG_FILE     Configuration parameters (default: default.json)
  --nats-server SERVER   Nats server address
  --nats-port PORT       Nats server port
```

**Examples**:
```bash
# Show version
python src/indicators/traffic_indicators.py --version

# Use remote NATS server
python src/indicators/traffic_indicators.py \
  --nats-server production.nats.com --nats-port 4222

# Custom configuration
python src/indicators/traffic_indicators.py --conf /etc/indicators/custom.json
```

## Verifying Installation

### Check Component Status

1. **Verify NATS connectivity**:
   ```bash
   # Install NATS CLI tools
   curl -sf https://binaries.nats.dev/nats-io/natscli/nats@latest | sh
   
   # Test connection
   ./nats server info
   ```

2. **Monitor input data streams**:
   ```bash
   # Monitor detector events
   ./nats sub "detector.status.*"
   
   # Monitor signal groups
   ./nats sub "group.status.270.*"
   
   # Monitor radar data
   ./nats sub "radar.270.*.objects_port.json"
   ```

3. **Monitor output data streams**:
   ```bash
   # Monitor traffic indicators
   ./nats sub "group.e3.270.*"
   ```

### Test Configuration

```bash
# Validate configuration syntax
python -c "import json; print('Valid JSON') if json.load(open('models/testmodel/indicators.json')) else None"

# Test configuration loading
python -c "from src.indicators.confread import GlobalConf; conf = GlobalConf(conf='models/testmodel/indicators.json'); print('Configuration loaded successfully')"
```

## Integration with Open Controller

### Docker Compose Integration

The component is part of the Open Controller suite. Use the main docker-compose.yaml:

```yaml
services:
  nats:
    image: nats:latest
    ports:
      - "4222:4222"
  
  indicators:
    build:
      context: .
      dockerfile: docker/indicators/Dockerfile
    depends_on:
      - nats
    environment:
      - NATS_SERVER=nats
```

### Running Multiple Components

```bash
# Start NATS and indicators together
docker-compose up nats indicators

# Start entire Open Controller stack
docker-compose up
```

## Performance Considerations

### Resource Usage
- **Memory**: ~50MB base + data buffers
- **CPU**: Low usage, spikes during data processing
- **Network**: Depends on sensor data frequency

### Scaling
- Single instance handles typical intersection data
- For high-frequency radar data, consider resource monitoring
- NATS server can be clustered for high availability

### Monitoring

Add monitoring for production deployment:
```bash
# Monitor container resources
docker stats indicators

# Monitor NATS message rates
./nats server report jetstream

# Application logs
docker logs -f indicators
```

## Common Issues

See [Troubleshooting](troubleshooting.md) for detailed problem resolution.

### Quick Fixes

**NATS connection failed**:
- Verify NATS server is running: `docker ps` or `ps aux | grep nats`
- Check network connectivity: `telnet localhost 4222`

**No input data**:
- Verify data sources are publishing: `./nats sub "detector.status.*"`
- Check configuration file paths and subjects

**Permission errors**:
```bash
# Fix file permissions
chmod +x docker/indicators/run_indicators.sh
sudo chown -R $USER:$USER /path/to/open_controller
```

**Python import errors**:
```bash
# Ensure you're in the correct directory
cd /path/to/open_controller
export PYTHONPATH="${PYTHONPATH}:/path/to/open_controller/src/indicators"
```
