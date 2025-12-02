# Troubleshooting

Common issues, diagnostics, and solutions for the Traffic Indicators component.

## Connection Issues

### NATS Server Connection Failed

**Symptoms**:
- Component exits immediately
- Error: "Connection refused" or "No servers available"
- No data processing occurs

**Diagnosis**:
```bash
# Check if NATS server is running
ps aux | grep nats-server
docker ps | grep nats

# Test NATS connectivity
telnet localhost 4222
# or
nc -zv localhost 4222
```

**Solutions**:
1. **Start NATS server**:
   ```bash
   # Standalone
   nats-server
   
   # Docker
   docker run -p 4222:4222 nats:latest
   
   # Docker Compose
   docker-compose up nats
   ```

2. **Check server configuration**:
   - Verify server address in configuration file
   - Confirm port number (default: 4222)
   - Check firewall settings

3. **Network issues**:
   ```bash
   # For Docker containers, use service name
   --nats-server nats  # not localhost
   
   # For remote servers, verify connectivity
   ping remote-nats-server
   ```

### No Input Data Received

**Symptoms**:
- Component starts but no processing occurs
- Output topics remain empty
- No error messages in logs

**Diagnosis**:
```bash
# Monitor input topics
nats sub "detector.status.*"
nats sub "group.status.270.*"
nats sub "radar.270.*.objects_port.json"

# Check if anyone is publishing
nats pub "detector.status.test" '{"id":"test","loop_on":true,"tstamp":"2025-01-01T00:00:00Z"}'
```

**Solutions**:
1. **Verify data sources**:
   - Ensure SUMO simulation is running and publishing
   - Check real sensor connections
   - Verify topic names match configuration

2. **Configuration issues**:
   ```bash
   # Validate configuration file
   python -c "import json; json.load(open('models/testmodel/indicators.json'))"
   
   # Check input stream subjects
   grep -A5 "input_streams" models/testmodel/indicators.json
   ```

3. **Subscription issues**:
   - Check NATS permissions
   - Verify wildcard patterns in subjects
   - Review component startup logs

## Configuration Issues

### Configuration File Not Found

**Error**: `File does not exist: config_file.json`

**Solutions**:
1. **Specify correct path**:
   ```bash
   # Use absolute path
   python src/indicators/traffic_indicators.py --conf /full/path/to/indicators.json
   
   # Use relative path from project root
   python src/indicators/traffic_indicators.py --conf models/testmodel/indicators.json
   ```

2. **Create configuration file**:
   ```bash
   # Copy from example
   cp models/testmodel/indicators.json my_config.json
   ```

### Invalid JSON Configuration

**Error**: `JSON decode error` or `Expecting property name`

**Diagnosis**:
```bash
# Validate JSON syntax
python -m json.tool models/testmodel/indicators.json

# Check for common JSON errors
cat models/testmodel/indicators.json | jq .
```

**Solutions**:
1. **Common JSON fixes**:
   - Remove trailing commas
   - Ensure all strings are quoted
   - Check bracket/brace matching
   - Verify escape sequences

2. **Use validation tools**:
   ```bash
   # Online validators or
   jsonlint models/testmodel/indicators.json
   ```

## Runtime Issues

### High Memory Usage

**Symptoms**:
- Component memory grows over time
- System becomes unresponsive
- Out of memory errors

**Diagnosis**:
```bash
# Monitor memory usage
docker stats indicators
top -p $(pgrep -f traffic_indicators)
```

**Solutions**:
1. **Enable data cleanup**:
   - Verify cleanup tasks are running
   - Check cleanup intervals in configuration
   - Monitor old data accumulation

2. **Reduce data retention**:
   ```python
   # Adjust in fusion2.py
   RADAR_PAST_MEASUREMENTS = 1  # Reduce from higher values
   ```

3. **Restart periodically**:
   ```bash
   # Add to crontab for production
   0 2 * * * docker restart indicators
   ```

### No Output Data Generated

**Symptoms**:
- Input data flows correctly
- Component runs without errors
- Output topics (`group.e3.270.*`) remain empty

**Diagnosis**:
```bash
# Check output configuration
grep -A10 "outputs" models/testmodel/indicators.json

# Monitor output attempts
nats sub "group.e3.270.>"

# Enable debug logging (modify source if needed)
```

**Solutions**:
1. **Configuration validation**:
   - Verify output stream configuration
   - Check lane assignments match input streams
   - Ensure detector/radar references are correct

2. **Field of view issues**:
   - Check radar lane assignments
   - Verify detector in/out assignments
   - Review coordinate mappings

### Data Processing Delays

**Symptoms**:
- Output timestamps lag significantly behind input
- Processing appears slow or blocked
- Inconsistent output frequency

**Solutions**:
1. **Check async task performance**:
   - Monitor background task execution
   - Verify no blocking operations in callbacks
   - Review cleanup task intervals

2. **Network bottlenecks**:
   - Monitor NATS server performance
   - Check network latency to data sources
   - Consider local NATS deployment

## Docker-Specific Issues

### Container Exits Immediately

**Diagnosis**:
```bash
# Check container logs
docker logs indicators

# Run interactively for debugging
docker run -it --entrypoint /bin/bash traffic-indicators
```

**Solutions**:
1. **Permission issues**:
   ```bash
   # Fix script permissions
   chmod +x docker/indicators/run_indicators.sh
   ```

2. **Missing dependencies**:
   ```bash
   # Rebuild with clean cache
   docker build --no-cache -f docker/indicators/Dockerfile -t traffic-indicators .
   ```

### Network Connectivity in Docker

**Issue**: Container cannot reach NATS server

**Solutions**:
1. **Use Docker networks**:
   ```yaml
   # docker-compose.yml
   services:
     nats:
       container_name: nats
     indicators:
       depends_on: [nats]
       environment:
         - NATS_SERVER=nats  # Use service name
   ```

2. **Host networking**:
   ```bash
   docker run --network host traffic-indicators
   ```

## Logging and Diagnostics

### Enable Debug Logging

**Modify source code** (temporary debugging):
```python
# Add to traffic_indicators.py main()
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Log Analysis

**Key log patterns to look for**:
```bash
# Connection issues
grep -i "connection" /var/log/indicators.log

# Configuration problems
grep -i "config\|conf" /var/log/indicators.log

# Data processing issues
grep -i "error\|exception" /var/log/indicators.log
```

### Performance Monitoring

```bash
# Monitor NATS message rates
nats server report connections

# Monitor component resource usage
docker stats indicators --no-stream

# Monitor output message frequency
nats sub "group.e3.270.>" | ts
```

## Testing and Validation

### End-to-End Test

1. **Start dependencies**:
   ```bash
   docker-compose up nats
   ```

2. **Inject test data**:
   ```bash
   # Test detector event
   nats pub "detector.status.test" '{"id":"detector.status.test","loop_on":true,"tstamp":"2025-01-01T00:00:00Z"}'
   
   # Test group status
   nats pub "group.status.270.1" '{"id":"group.status.270.1","tstamp":"2025-01-01T00:00:00Z","substate":"g"}'
   ```

3. **Monitor outputs**:
   ```bash
   nats sub "group.e3.270.*"
   ```

### Configuration Testing

```bash
# Test configuration loading
python -c "
from src.indicators.confread import GlobalConf
try:
    conf = GlobalConf(conf='models/testmodel/indicators.json')
    print('Configuration loaded successfully')
    print(conf.get_json_str(prettyprint=True))
except Exception as e:
    print(f'Configuration error: {e}')
"
```

## Getting Help

### Log Collection

When reporting issues, collect:

```bash
# Component logs
docker logs indicators > indicators.log 2>&1

# NATS server status
nats server info > nats_status.txt

# System information
uname -a > system_info.txt
docker version >> system_info.txt
```

### Common Environment Info

```bash
# Python environment
python --version
pip list | grep -E "nats|jsmin"

# Docker environment
docker version
docker-compose version

# Network configuration
ifconfig | grep -A1 "inet"
netstat -tlnp | grep 4222
```

### Minimal Reproduction

For bug reports, create minimal configuration:

```json
{
  "connectivity": {"nats": {"server": "localhost", "port": 4222}},
  "input_streams": {
    "test_detector": {
      "connection": "nats",
      "type": "detectors",
      "nats_subject": "detector.status.test"
    }
  },
  "outputs": {
    "test_view": {
      "type": "e3",
      "nats_output_subj": "group.e3.test",
      "lanes": {"test_lane": {"name": "test"}}
    }
  }
}
```
