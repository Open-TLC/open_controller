![Open Controller Logo](./services/user_interfaces/src/assets/OC_logo_green_horizontal.jpg)

# About 

This is the main repository of Open Controller, an open source traffic light controller.
The main idea of Open Controller is to separate data processing from signal control, which
makes it possible to develop new algorithms for traffic signal control.
Open Controller was developed in the [Smart Junction](https://www.aalto.fi/en/department-of-built-environment/smart-junction) project in cooperation between
[City of Helsinki](https://www.hel.fi/en/decision-making/city-organisation/divisions/urban-environment-division), 
[Aalto University](https://www.aalto.fi/en/department-of-built-environment/spatial-planning-and-transportation-engineering) and 
[Conveqs Oy](https://www.conveqs.fi). During the project a new control algorithm was developed
which is based on a holistic understanding of the traffic situation in real time.
The holistic traffic situation is based on ordinary detectors and on new sensor types like radars, cameras and V2X.

An overview of the system architecture and the messaging between the
services is given in [doc/architecture.md](doc/architecture.md).

![open_controller_overview](/doc/images/open_controller_overview2.png)
*Figure 1: Overview of the Open Controller*

# Quickstart

To run the basic system, you need to have [Docker](https://docs.docker.com/get-started/get-docker/)
and `make` installed on your system. Then, in the repository folder:

    make up

(equivalent to `docker compose up --build`). This builds and starts the full
Open Controller stack, six containers in total:

- **NATS server**, a standard [NATS](https://nats.io) message broker
- **Clockwork**, the open source traffic light control engine
- **Traffic Indicators**, which compute indicators from the sensor data
- **Simengine**, a [SUMO](https://eclipse.dev/sumo/) simulation platform with interfaces to access Open Controller
- **UI**, a user interface for the system
- **WebSUMO**, a browser-based viewer for the running simulation

After this you should be able to see the user interface via [http://127.0.0.1:8050](http://127.0.0.1:8050)
and watch the simulation itself in the WebSUMO viewer via [http://127.0.0.1:8775](http://127.0.0.1:8775).

The integrated simulation (controller and simulator in one process, see below) has
its own smaller stack:

    make integrated

which starts NATS, the integrated simengine and the WebSUMO viewer
(defined in `integrated.compose.yaml`).

# Basic usage

To get started, clone the Open Controller repository to your local computer. You need to have [Git](https://github.com/git-guides/install-git) installed on your computer.
Go to the Open Controller repository in your web browser. Press the "Code" button and copy the command, then paste it into a terminal in your local directory. You may need to
install SSH if you use that option for cloning.

    git clone git@github.com:Open-TLC/open_controller.git

Open Controller can be used in several ways. When starting a new project, it is recommended to test everything in simulation.
The simulator used with Open Controller is [SUMO](https://eclipse.dev/sumo/) ("Simulation of Urban Mobility"). SUMO is an open source
traffic simulator that comes with many features useful for running and testing Open Controller. Open Controller communicates
with the simulator through SUMO's [libsumo](https://sumo.dlr.de/docs/Libsumo.html) interface.

The available modes for using Open Controller are the following:
1) Integrated simulation
2) Distributed simulation
3) Hardware-in-the-loop simulation
4) Live operation (controlling the traffic in the field).

A simple way to get started with Open Controller is option 1 (integrated simulation), which is commonly used for evaluating signal control performance.
With integrated simulation, it is possible to run several Open Controllers in one simulation scenario.

![sim_integrated](/doc/images/sim_integrated.png)
*Figure x: Integrated simulation*

The second option is to use the distributed simulation, in which the simulation is separated from the controller. This way it is possible 
to test that the communication and messages needed in the actual signal control are working properly.

The third option is Hardware-in-the-loop simulation, which is similar to distributed simulation, except that the actual signal controller
device is included in the control loop. This way everything can be tested to the last detail before live operation.

![hwil_sim](/doc/images/hwil_sim.png)
*Figure x: Hardware-in-the-loop simulation*

The last option is live signal control in the field, in which the simulator is no longer involved. All inputs come from real sensors and the signal control
output commands are sent to the actual roadside device, which carries out control of the real traffic.

![live_control](/doc/images/live_control.png)
*Figure x: Live signal control in the field*

It should be noted that the options 3 and 4 cannot be used without an interface component to the signal controller device. For safety
reasons this component cannot be shared publicly. Only the City of Helsinki can provide access to the real signal controllers.


## Using the integrated version

The simplest way to run Open Controller is so-called integrated simulation. In this case, no communication channels are needed
between the controller and the simulation, because Open Controller accesses the simulator directly through the libsumo interface.

The easiest way to run it is in containers:

    make integrated

To run it directly on your own computer instead, you need Python and the
project dependencies (managed with [uv](https://docs.astral.sh/uv/); `uv sync`
installs them from `pyproject.toml`). The controller takes a YAML
configuration file as a command-line parameter. The demo model below is from
the Jätkäsaari test region junctions 266-267 (266 is under the bridge):

    cd "mydirectory"/open_controller
    uv run -m services.simengine.src.simengine_integrated --conf-file models/JS_266-267_DEMO/contr/JS2_266-267_DEMO.yaml

The configuration file includes everything needed to run Open Controller with
SUMO, including the path of the SUMO configuration file; the format is
documented in
[services/control_engine/doc/configuration.md](services/control_engine/doc/configuration.md).

Open Controller takes a time step (default value = 0.1 sec), reads detector data from SUMO and updates its own internal states.
Finally, it sends the new traffic signal states to SUMO and continues with the next update. The integrated simulation can be run in real time
or at full speed depending on the timer settings (see the configuration section).

Note that the simulation runs windowless: libsumo does not support SUMO's
graphical mode. The simulation is instead viewed in a browser with the
WebSUMO viewer (started by `make integrated`; see
[services/simengine/doc/websumo.md](services/simengine/doc/websumo.md)).
The viewer can be disabled with the `--nowebsumo` option.

## Running multiple Open Controllers

Several Open Controllers can run in the same simulation. They are defined in
the same YAML configuration file: the `clockwork` section takes a list of
`controllers`, each with its own id, controller type and options. See
[configuration/template.yaml](configuration/template.yaml) for a commented
example and
[services/control_engine/doc/configuration.md](services/control_engine/doc/configuration.md)
for the full reference.

## Using the distributed version

### What comes with the package
The Open Controller system consists of separate services communicating with each other via pub/sub messages (see Figure 2). The messaging broker used in the implementation is [NATS](https://nats.io), running in its own Docker container on standard port 4222. The services, each running in its own container, are:

- **Clockwork**, the signal group control engine 
- **Simengine**, a SUMO simulation environment with Open Controller interfaces
- **Traffic Indicators**, processing the sensor data into traffic situation indicators 
- **User Interface**, user interfaces for monitoring and controlling the services
- **WebSUMO**, a browser-based viewer following the simulation over NATS

![Open Controller Docker Services](/doc/images/OC_Docker_Services2.png)
*Figure 2: Open Controller Standard Services*

**Simengine** is a service for running [SUMO](https://eclipse.dev/sumo/) simulation in real time and providing an interface for exchanging messages between the SUMO model and other applications and services. The simulation works as a simulated "reality" and provides similar outputs to those one would get from field devices, namely:

- *Detector statuses* (induction detector determining if there is a vehicle over certain area)
- *Signal Group statuses* (status of traffic lights), and
- *Radar statuses* (object list of vehicles in a predetermined area)

In addition, simengine can also receive *Signal Group control* messages dictating the statuses of the signal groups (traffic lights) in the model. This is used for controlling the traffic controllers in the simulation model.

**Traffic Indicators** process sensor data into traffic indicators that can be used as input for signal control. Traffic indicators are not needed if only detector data is used as input. When radar or camera data is used, the traffic indicators component is needed.

**Clockwork** is a signal-group-oriented control engine which can operate in various modes. The basic mode is based on detectors, detector logics and signal groups performing traffic light control similar to most controllers in use.
In the basic mode the green extension is based on detector logics, which is looking for gaps in the vehicle flow to terminate the active green signal. In smart extender mode the control engine is still based on flexible signal group phasing,
but the timing is based on a more holistic view of the traffic situation. The smart green extender can not only extend its own green, but also cut the conflicting active green in order to start earlier.

Clockwork subscribes to data inputs (e.g. detector statuses) and provides signal control commands (*Signal Group Control* messages) as an output. It should be noted that this unit can be used both with a simulator and with real traffic controllers,
given that there is an interface for relaying them to the controller (this part is not provided at the time of writing due to IP restrictions).

**User Interfaces** are tools for monitoring and controlling the state of Open Controller. User interfaces are either native programs or browser-based tools. Various user interfaces are available or under development.

To run the basic system you need to have [Docker](https://docs.docker.com/get-started/get-docker/) installed on your system. In a Windows environment, you may need to install Windows Subsystem for Linux (WSL) 2. Then run:

    make up

After this you should be able to see the user interface via [http://127.0.0.1:8050](http://127.0.0.1:8050),
and the simulation itself in the WebSUMO viewer via [http://127.0.0.1:8775](http://127.0.0.1:8775)
(pick the scenario, Load, Start).

## Operating the user interface
For most users, the first interaction with the system will be via the UI component. When the system is running, it can be accessed on localhost port 8050 (i.e. [http://127.0.0.1:8050](http://127.0.0.1:8050)).

## Monitoring the messages
In order to monitor the messages, you will need a NATS client. Installation depends on your operating system, and the instructions can be found [here](https://docs.nats.io/running-a-nats-service/clients). Note that the server itself is not needed, since it is provided in its own container and is accessible via the standard port on the host. You can subscribe to all NATS messages by issuing the command

    nats sub ">"

You can also subscribe to one or many subjects by replacing `">"` with a subject. Wildcards (`"*"` ) are also possible. For example, you can subscribe to all detector status messages by issuing:

    nats sub "detector.status.*"

The main subjects are listed in Table 1; the message formats and the
communication patterns between the services are described in
[doc/architecture.md](doc/architecture.md).

*Table 1: The open controller data stream subjects*
| Subject prefix    | Source         | Example                      | Description                            |
| ----------------- | -------------- | ---------------------------- | -------------------------------------- |
| detector.status   | simengine      | detector.status.1-001        | Status of a detector (occupied or not) |
| group.status      | simengine      | group.status.270.1           | Realised status of a traffic light     |
| radar             | simengine      | radar.270.2.objects.json     | Radar object list                      |
| group.control     | clockwork      | group.control.270.1          | Control message of a traffic light     |
| clockwork.command | other services | clockwork.command            | Commands to the control engine         |
| clockwork.status  | clockwork      | clockwork.status             | Control engine status (request-reply)  |
| sim               | simengine      | sim.JS270_DEMO.state         | Simulation state for the WebSUMO viewer |

## Installing and running individual components
### Two methods for operating the system

There are two main methods for running and using the Open Controller components: 1) running them in their own Docker containers (this is the method used in the Quickstart), and 2) running them on your local computer or a server. Both methods have their benefits.

Running the system with Docker is relatively straightforward and makes it easy to deploy in different environments. However, debugging and developing new features might be more troublesome. Note that SUMO runs windowless in all setups (libsumo has no graphical mode) - the simulation is viewed with the WebSUMO container instead.

Running the components on a local computer (or a server in the cloud), on the other hand, has its own drawbacks. The biggest nuisance is the need to install and configure many different libraries and components. The project's Python dependencies are managed with [uv](https://docs.astral.sh/uv/) (`uv sync`).

It should be noted that it is possible, and recommended, to use the Docker installation as a basis for operation and run only the required parts locally.

### Operating the Open Controller docker containers

The Open Controller containers can be operated like any other containers in the system by starting and stopping them using the Docker user interface. They can also be started and stopped from the command line by issuing commands such as

    # Stopping the Simengine (SUMO) container
    docker container stop oc_simengine_container

And started in a similar manner:

    # Starting the Simengine (SUMO) container
    docker container start oc_simengine_container

The container names are: `oc_clockwork`, `oc_simengine_container`,
`oc_indicators_container`, `oc_ui_container` and `oc_websumo_container`.
This is useful especially when running only one part of the Open Controller
package locally and relying on containers for the rest of the package.

# Configuration

Open Controller is being moved to a single YAML configuration: one file that
can hold the settings of all services (or be split per service), with shared
general settings. The YAML format is documented in
[services/control_engine/doc/configuration.md](services/control_engine/doc/configuration.md),
and a commented template is provided in
[configuration/template.yaml](configuration/template.yaml). Clockwork and the
integrated simulation engine already use the YAML format.

The migration is staged: the independent simulation engine and Traffic
Indicators still read their previous JSON configuration files, and the model
directories still contain the legacy JSON controller configurations alongside
the new YAML ones. These will be migrated in later stages.

Old JSON controller configurations can be converted to the new YAML format
with the converter tool:

    uv run python tools/conf_convert.py -i models/JS270_DEMO/contr/JS270_DEMO.json -o models/JS270_DEMO/contr/JS270_DEMO.yaml

Check the generated file manually after conversion.

## Simulation engine

The simulation engine (simengine for short) is a software component that runs the SUMO traffic simulator, collects data from detectors and sensors
and generates the messages to the controller through NATS. The simengine can also receive messages which control the traffic signals or vehicles (through V2X).
The integrated engine is configured with the central YAML file; the independent engine still uses its JSON configuration (legacy, staged for migration).
Instructions for configuration can be found here: [Configuration of the simengine](services/simengine/doc/configuration.md)

## Traffic Indicators

Traffic Indicators is a component that reads various sensor data and computes traffic situation indicators for the control engine. Currently, Traffic Indicators can accept
data from detectors, radars and AI cameras. However, in the future this component can be extended to new sensor types and new data sources. The indicators for signal control currently
involve queue counts (signal state red) and the number of approaching vehicles (signal state green). These indicators can be enhanced in the future.
Traffic Indicators still uses its JSON configuration (legacy, staged for migration).
Further instructions can be found in [Configuration of the traffic indicators](services/indicators/doc/configuration.md)

## Control engine

The core component of Open Controller is the signal group based control engine, Clockwork. It is configured with the central YAML file:
[Configuration of the controller](services/control_engine/doc/configuration.md)

# Development

Linting and the test suites are run through the Makefile:

    make lint          # ruff
    make build-test    # build the unit test image
    make test          # run the unit tests (tests/unit)

The integration test (`tests/integration`) runs the integrated simulation in
a container and fails if it crashes.

# Documentation and further reading

- [doc/architecture.md](doc/architecture.md) - system architecture and the NATS messaging between the services
- [services/control_engine/doc/configuration.md](services/control_engine/doc/configuration.md) - the YAML configuration reference
- [services/control_engine/doc/signal_group_operation.md](services/control_engine/doc/signal_group_operation.md) - signal group state machine
- [services/simengine/doc/websumo.md](services/simengine/doc/websumo.md) - viewing the simulation with WebSUMO
- [README_SIM_MODEL.md](README_SIM_MODEL.md) - working with the simulation models

# Links and other material

The [Open Controller web page](https://www.opencontroller.org): 

# License

The software is released under the EUPL-1.2 licence. Click [here](https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12) for more details.
