![Open Controller Logo](/src/ui/assets/OC_logo_green_horizontal.jpg)

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

![open_controller_overview](/doc/images/open_controller_overview.png)
*Figure 1: Overview of the Open Controller*

# Quickstart

To run the basic system, you need to have Docker installed on your system.

After this, you can set up the full Open Controller system and run it with a relatively simple test model by issuing the following command (in the repository folder):

    docker-compose up

This script will, in essence, install four separate Docker containers and run them:

- **NATS server**, a standard NATS message broker
- **Control engine**, the open source traffic light controller
- **Traffic indicators**, which compute indicators from the sensor data
- **Simengine**, a SUMO simulation platform with interfaces to access Open Controller
- **UI**, a user interface for the system

After this you should be able to see the user interface via http://127.0.0.1:8050

# Basic usage

To get started, clone the Open Controller repository to your local computer. You need to have [Git](https://github.com/git-guides/install-git) installed on your computer.
Go to the Open Controller repository in your web browser. Press the "Code" button and copy the command, then paste it into a terminal in your local directory. You may need to
install SSH if you use that option for cloning.

    git clone git@github.com:Open-TLC/open_controller.git

Open Controller can be used in several ways. When starting a new project, it is recommended to test everything in simulation.
The simulator used with Open Controller is [SUMO](https://eclipse.dev/sumo/) ("Simulation of Urban Mobility"). SUMO is an open source
traffic simulator that comes with many features useful for running and testing Open Controller. SUMO offers an interface called
TraCI that allows Open Controller to communicate with the simulator.

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
between the controller and simulation, because Open Controller accesses the simulator using direct commands through the TraCI interface.
To run the integrated version, you need to install SUMO, Python and some Python libraries: (list here).

To run Open Controller in integrated mode, call the controller in Python and provide a configuration file path as a
command-line parameter (see the example below). Open a terminal on your computer and go to the `open_controller` directory.
Copy the command below and press Enter. The demo model is from the Jätkäsaari test region junction 270 (in front of the Clarion Hotel) with the smart green extension included.

    cd "mydirectory"/open_controller
    python services/simengine/src/simengine_integrated.py  --conf-file models/JS270_DEMO/contr/JS270_DEMO.json --print-status --graph
    
The configuration file includes everything needed to run Open Controller with SUMO. The SUMO configuration file must
be given within the Open Controller configuration file. The `print-status` option sets Open Controller to print status data to the console.
The `graph` option enables graphical mode for visualizing the intersection and traffic. The options can also be defined in the
`sumo` section of the Open Controller configuration (see below). Command-line options always override the configuration file settings.

```json
"sumo":{
    "print-status": true,
    "graph" : true,
    "file_name": "models/JS270_DEMO/cfgFiles/JS270_DEMO.sumocfg"
    }
```

Open Controller takes a time step (default value = 0.1 sec), reads detector data from SUMO and updates its own internal states.
Finally, it sends the new traffic signal states to SUMO and continues with the next update. The integrated simulation can be run in real time
or at full speed depending on timer settings (see the configuration section).

## Running multiple Open Controllers

In simulation it is possible to run several Open Controllers at the same time. In this case, the same Python script can be used, but the file format
is different. The file that is given as command-line parameter has the basic definition of the simulation but the parameters for each controller
are given in separate files, which are defined in the main file. The demo model below is from the Jätkäsaari test region junctions 266-267
(266 is under the bridge) with the smart green extension included. In this demo the junctions are controlled independently without mutual coordination.
 
    cd "mydirectory"/open_controller
    python services/simengine/src/multi_sumo_int_graph.py --conf-file models/JS_266-267_DEMO/contr/JS2_266-267_DEMO.json


It is possible to use an external LibSumo component instead of TraCI, which makes the simulation much faster. However, LibSumo does not support
graphical mode and there can be some known issues with installation of LibSumo on Windows.

## Using the distributed version

### What comes with the package
The Open Controller system consists of separate services communicating with each other via pub/sub messages (see Figure 2). The messaging broker used in the implementation is [NATS](https://nats.io), running in its own Docker container on standard port 4222. There are three services, each running in its own container:

- **Control Engine**, the signal group control engine 
- **Simengine**, a SUMO simulation environment with Open Controller interfaces
- **Traffic Indicators**, processing the sensor data into traffic situation indicators 
- **User Interface**, user interfaces for monitoring and controlling the services

![Open Controller Docker Services](/doc/images/OC_Docker_Services2.png)
*Figure 2: Open Controller Standard Services*

**Simengine** is a service for running [SUMO](https://eclipse.dev/sumo/) simulation in real time and providing an interface for exchanging messages between the SUMO model and other applications and services. The simulation works as a simulated "reality" and provides similar outputs to those one would get from field devices, namely:

- *Detector statuses* (induction detector determining if there is a vehicle over certain area)
- *Signal Group statuses* (status of traffic lights), and
- *Radar statuses* (object list of vehicles in a predetermined area)

In addition, simengine can also receive *Signal Group control* messages dictating the statuses of the signal groups (traffic lights) in the model. This is used for controlling the traffic controllers in the simulation model.

**Traffic Indicators** process sensor data into traffic indicators that can be used as input for signal control. Traffic indicators are not needed if only detector data is used as input. When radar or camera data is used, the traffic indicators component is needed.

**Control Engine** is a signal-group-oriented control engine which can operate in various modes. The basic mode is based on detectors, detector logics and signal groups performing traffic light control similar to most controllers in use.
In the basic mode the green extension is based on detector logics, which is looking for gaps in the vehicle flow to terminate the active green signal. In smart extender mode the control engine is still based on flexible signal group phasing,
but the timing is based on a more holistic view of the traffic situation. The smart green extender can not only extend its own green, but also cut the conflicting active green in order to start earlier.

The Control engine subscribes to data inputs (e.g. detector statuses) and provides signal control commands (*Signal Group Control* messages) as an output. It should be noted that this unit can be used both with a simulator and with real traffic controllers,
given that there is an interface for relaying them to the controller (this part is not provided at the time of writing due to IP restrictions).

**User Interfaces** are tools for monitoring and controlling the state of Open Controller. User interfaces are either native programs or browser-based tools. Various user interfaces are available or under development.


To run the basic system you need to have [Docker](https://docs.docker.com/get-started/get-docker/) installed on your system. In a Windows environment, you may need to install Windows Subsystem for Linux (WSL) 2.

After this you can set up the full Open Controller system and run it with a relatively simple test model by issuing the command:

    docker compose up

This script will, in essence, install four separate Docker containers and run them:

- NATS server, a standard [NATS](https://nats.io) message broker
- Control engine, the open source traffic light controller
- Simengine, a [SUMO](https://eclipse.dev/sumo/) simulation platform with interfaces to access Open Controller
- UI, a user interface for the system

After this you should be able to see the user interface via [http://127.0.0.1:8050](http://127.0.0.1:8050)

Note that the simulation model in this example is run inside a container without a UI. If you wish to see the intersection in operation, you will need to run SUMO and simengine locally in graphical mode. How to do this is explained [here](#installing-and-running-simengine-in-local-computer).

## Operating the user interface
For most users, the first interaction with the system will be via the UI component. When the system is running, it can be accessed on localhost port 8050 (i.e. [http://127.0.0.1:8050](http://127.0.0.1:8050)).

## Monitoring the messages
In order to monitor the messages, you will need a NATS client. Installation depends on your operating system, and the instructions can be found [here](https://docs.nats.io/running-a-nats-service/clients). Note that the server itself is not needed, since it is provided in its own container and is accessible via the standard port on the host. You can subscribe to all NATS messages by issuing the command

    nats sub ">"

You can also subscribe to one or many subjects by replacing `">"` with a subject. Wildcards (`"*"` ) are also possible. For example, you can subscribe to all detector status messages by issuing:

    nats sub "detector.status.*"

The full list of channels is given in Table 1, and a more detailed description of message types and the data they contain is available [here](https://www.opencontroller.org/).

*Table 1: The open controller data stream subjects*
| Subject prefix   | Source    | Example                      | Description                           |
| ---------------- | --------- | ---------------------------- | ------------------------------------- |
| detector.status  | simengine | detector.status.1-001        | Status of a detector (occupied or not) |
| group.status     | simengine | group.status.270.1           | Status of a traffic light             |
| radar            | simengine | radar.270.2.objects.json     | Radar object list                     |
| controller       | control engine | controller.status.270        | Open controller status                |
| group.control    | control engine | group.control.270.1          | Control message of a traffic light    |

## Installing and running individual components
### Two methods for operating the system

There are two main methods for running and using the Open Controller components: 1) running them in their own Docker containers (this is the method used in the Quickstart), and 2) running them on your local computer or a server. Both methods have their benefits.

Running the system with Docker is relatively straightforward and makes it easy to deploy in different environments. However, debugging and developing new features might be more troublesome. In addition, at least in the current setup, SUMO can only be run in non-graphical mode inside Docker.

Running the components on a local computer (or a server in the cloud), on the other hand, has its own drawbacks. The biggest nuisance is the need to install and configure many different libraries and components. In the following, short instructions are given for both methods.

It should be noted that it is possible, and recommended, to use the Docker installation as a basis for operation and run only the required parts locally (e.g. the graphical version of Simclient).

### Operating the Open Controller docker containers

The Open Controller containers can be operated like any other containers in the system by starting and stopping them using the Docker user interface. They can also be started and stopped from the command line by issuing commands such as

    # Stopping the Simengine (SUMO) controller
    docker container stop oc_simengine_container

And started in a similar manner:

    # Starting the Simengine (SUMO) controller
    docker container start oc_simengine_container

This is useful especially when running only one part of the Open Controller package locally and relying on containers for the rest of the package.

### Installing and running components to a local computer

#### Installing and running simengine in local computer

[comment]: <> (Installation to a local machine here)


# Configuration

[comment]: <> (Command line arguments under this also)

## Simulation engine

The simulation engine (simengine for short) is a software component that runs the SUMO traffic simulator, collects data from detectors and sensors
and generates the messages to the controller through NATS. The simengine can also receive messages which control the traffic signals or vehicles (through V2X).
Instructions for configuration can be found here: [Configuration of the simengine](https://github.com/Open-TLC/open_controller/blob/main/services/simengine/doc/configuration.md)

## Traffic Indicators

Traffic Indicators is a component that reads various sensor data and computes traffic situation indicators for the control engine. Currently, Traffic Indicators can accept
data from detectors, radars and AI cameras. However, in the future this component can be extended to new sensor types and new data sources. The indicators for signal control currently
involve queue counts (signal state red) and the number of approaching vehicles (signal state green). These indicators can be enhanced in the future.
Further instructions can be found in [Configuration of the traffic indicators](https://github.com/Open-TLC/open_controller/blob/main/services/indicators/doc/configuration.md)

## Control engine

The core component of Open Controller is the signal group based control engine. The control engine (previously referred to as the clockwork) can be configured using the following instructions:
[Configuration of the controller](https://github.com/Open-TLC/open_controller/blob/main/services/control_engine/doc/configuration.md)

## User Interface

# Documentation and further reading

[comment]: <> (Links to : sysarch, theory and maybe to something else)

# Links and other material

The [Open Controller web page](https://www.opencontroller.org): 

# License

The software is released under the EUPL-1.2 licence. Click [here](https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12) for more details.
