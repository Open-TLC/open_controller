# Changelog

All notable changes to the Traffic Indicators component will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- HSL API integration for real-world data sources
- Enhanced vehicle classification algorithms
- Performance optimizations for high-frequency data
- Real-time configuration updates
- Advanced traffic pattern detection

## [0.1.0] - 2025-12-02

### Added
- Initial implementation of Traffic Indicators component
- NATS-based messaging for sensor data ingestion
- Support for three input data types:
  - Signal group status from traffic controllers
  - Loop detector events from road sensors
  - Radar object tracking from traffic monitoring systems
- Field of View processing for traffic analysis
- Traffic indicator output generation (E3 format)
- Docker containerization support
- JSON-based configuration system
- Command line interface with parameter overrides
- Multi-sensor data fusion capabilities
- Background data cleanup tasks
- Async processing architecture

### Core Components
- `SensorTwin`: Main orchestration and sensor management
- `Radar`: Radar sensor data processing
- `Detector`: Loop detector event handling
- `Group`: Traffic signal group status management
- `FieldOfView`: Multi-sensor data fusion and analysis
- `GlobalConf`: Configuration management system

### Data Processing Features
- Vehicle classification mapping (radar classes to SUMO types)
- Quality-based object filtering
- Temporal data aggregation
- Vehicle counting with detector correlation
- Speed and acceleration analysis
- Lane-specific traffic indicators

### Configuration Support
- Flexible NATS connection configuration
- Multiple radar sensor inputs
- Configurable detector assignments
- Field of view lane mapping
- Output stream customization
- Environment variable overrides
- Command line parameter support

### Deployment Options
- Docker Compose integration
- Standalone Python execution
- Docker containerization
- Development and production configurations

### Documentation
- Component overview and architecture
- Input/output data specifications
- Configuration reference guide
- Installation and deployment instructions
- Troubleshooting guide

## Development History

The Traffic Indicators component was developed as part of the Open Controller project by Conveqs Oy and Kari Koskinen. It represents the evolution from basic traffic signal control to intelligent, data-driven traffic management systems.

### Design Principles
- **Modularity**: Clean separation of sensor types and processing logic
- **Scalability**: Async architecture supports high-frequency data streams
- **Flexibility**: Configuration-driven approach for various deployment scenarios
- **Reliability**: Error handling and automatic recovery mechanisms
- **Integration**: NATS messaging enables loose coupling with other components

### Technology Choices
- **Python 3.9+**: Modern Python features and performance
- **NATS**: High-performance messaging for real-time data
- **Async/Await**: Non-blocking processing for concurrent sensor streams
- **JSON**: Human-readable configuration and data formats
- **Docker**: Containerization for consistent deployment

## Known Limitations

### Current Version (0.1.0)
- Single intersection focus (designed for junction 270 in test model)
- SUMO simulation primarily tested (limited real-world sensor validation)
- Basic vehicle classification (limited to standard vehicle types)
- No historical data persistence (in-memory processing only)
- Manual configuration required for new intersections
- Limited error recovery for sensor failures

### Performance Characteristics
- Supports typical intersection data rates (10-100 Hz)
- Memory usage scales with data retention windows
- CPU usage minimal during steady-state operation
- Network bandwidth dependent on sensor data frequency

## Migration Notes

### Future Version Compatibility
- Configuration format may evolve (backward compatibility planned)
- NATS topic structure designed for stability
- Docker image versioning for deployment consistency
- API contracts will follow semantic versioning

### Upgrade Considerations
- Monitor configuration file format changes
- Review Docker image updates for breaking changes
- Test sensor data compatibility with new versions
- Validate output format compatibility with downstream consumers

## Contributing

### Development Workflow
1. Fork repository and create feature branch
2. Implement changes with appropriate tests
3. Update documentation for new features
4. Add changelog entry for notable changes
5. Submit pull request with detailed description

### Code Standards
- Follow Python PEP 8 style guidelines
- Add docstrings for new classes and methods
- Include type hints where appropriate
- Maintain async/await patterns for I/O operations
- Update configuration schema for new parameters

### Testing Requirements
- Unit tests for core processing logic
- Integration tests with NATS messaging
- Configuration validation tests
- Docker build and deployment tests
- Performance regression tests for high-frequency data

## Support

### Reporting Issues
- Use GitHub issues for bug reports and feature requests
- Include relevant log files and configuration
- Provide steps to reproduce problems
- Specify environment details (OS, Docker, NATS version)

### Getting Help
- Review troubleshooting guide for common issues
- Check configuration examples for setup guidance
- Consult installation guide for deployment problems
- Contact development team for integration support
