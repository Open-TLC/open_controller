9(![Open Controller Logo](/src/ui/assets/OC_logo_green_horizontal.jpg)

# About 

This is the main repository of Open Controller, an open source traffic light controller. 
The main idea of the open controller is to separate the data processing from signal control, which
makes it possible to develope new algorithms for traffic signal control.
The Open controller was developed in [Smart Junction](https://www.aalto.fi/en/department-of-built-environment/smart-junction) project in co-operation between 
[City of Helsinki](https://www.hel.fi/en/decision-making/city-organisation/divisions/urban-environment-division), 
[Aalto University](https://www.aalto.fi/en/department-of-built-environment/spatial-planning-and-transportation-engineering) and 
[Conveqs Oy](https://www.conveqs.fi). During the project a new control algorithm was developed
which is based on holistic undestanding of the traffic situation in real-time. 
The holistic traffic situation is based on ordinary detectors and on new sensor types like radars, cameras and V2X.

![Open Controller Overview](/doc/images/OpenController_Overview.png)
*Figure 1: Overview of the Open Controller*



# Basic usage

To get started clone the open controller repository to your own local computer. 
The open controller can be used in several ways. When starting a new project it is recommended to test everything within simulation. 
The simulator used with open controller is [SUMO](https://eclipse.dev/sumo/) "Simulation of Urban MObility". Sumo is an open source
traffic simulator which comes with many features useful in running and testing the open controller. Sumo offers and interface called
Traci to let the open controller to communicate with the simulator.

The available modes for using open controller are the following:
1) Integrated simulation
2) Distributed simulation
3) Hardware-in-the-loop simulation
4) Live operation (controlling the traffic in the field).

The easiest way to get started with the open controller is the option 1 (the integrated simulation), which is commonly used for evaluating the performance of the signal control.

The second option is to use the distributed simulation, in which the simulation is separated from the controller. This way it is possible 
to test that the communication and messages needed in the actual signal control are working properly.

The third option is the Hardware-in-the-loop simulation, which is similar to the distributed simulation, except thast the actual signal controller
device is included in the control loop. This way everything can be tested to the last detail before live operation.

The last option is live signal control in the field, in which the simulagtor is no more involved. All the inputs are coming from real sensors and the signal control
output commands are sent the the actual road side device, which carries out the control of the real traffic.

It should be noted that the options 3 and 4 cannot be used without an interface component to the signal controller device. For safety
reasons this component cannot be shared publicly. Only the City of Helsinki can provide access to the real signal controllers.


## Using the integrated version

The most simple way of running open controller is so called integrated simulation. In this case, no communication channels are needed
between the controller and simulation, because the the open controller access the simulator using direct commands through Traci-interface.

To run the opne controller in integrated mode, you call the controller in python and give a configuration file name and path as 
command line parameter. See the example below. 

    cd */open_controller
    python src/simengine/simengine_integrated.py  --conf-file models/JS270_DEMO/contr/JS270_DEMO.json --print-status --graph

The configuration file involves everything needed to run the open controller with Sumo. The Sumo configuration file can
be given within the open controller configuration file or as command line paramter. Sumo can be run with or without
graphic display. This can also be defined in the command line or in the open controller configuration (see below).

```json
"sumo":{
    "graph" : true,
    "file_name": "models/JS270_DEMO/cfgFiles/JS270_DEMO.sumocfg"
```

The open controller takes a time step (default value = 0.1 sec), reads the detector data from Sumo and updates its own internal states. 
Finally it send the new traffic signal states to the Sumo and continues with next update.
The integrated simulation can be run in real-time or with full speed depending on the available computing power.

In simulation it is possible to run several open controllers at the same time. In this case another Python script is used (multi_sumo_interface.py).
The multi-sumo version runn by default in console mode only. This way it can use the LibSumo component instead of Traci, which makes it much faster.
If you want to run multi-sumo in graphical mode, use the multi_sumo_int_graph.py.

    python src/clockwork/multi_sumo_interface.py --conf-file=models/testmodel/oc_demo.json 

    python src/clockwork/multi_sumo_int_graph.py --conf-file=models/testmodel/oc_demo.json 


## Using the distributed version

### What comes with the package
The open controller system consists of separate services communcating with each other via pub/sub messages (see Figure 2). The messaging broker used in the  implementation is [NATS](https://nats.io) service ran ion it's own docker container and standard port 4222. There are three services, each running in their own container:

- **Clockwork**, the core component of the Open Controller
- **Simengine**, a sumo simulation environment with Open Controller interfaces
- **Traffic Indicators**, processing the sensor data into traffic situation indicators 
- **User Interface**, an user interface for monitoring and controlling the services

![Open Controller Docker Services](/doc/images/OC_Docker_Services.png)
*Figure 2: Open Controller Standard Services*

**Simengine** is a service for running [SUMO](https://eclipse.dev/sumo/) simulation in real time and providing interface for exchang messages between the Sumo model and other applications and services. The simulation works as a simulated "reality" and provides similar outputs one would be getting from a field devices, namely:

- *Detector statuses* (induction detector determining if there is a vehicle over certain area)
- *Signal Group statuses* (status of traffic lights), and
- *Radar statuses* (object list of vehicles in pre-detemind area)

In addittion, simengine can also receive *Signal Group control* messsages dictating the statuses of the signal groups (traffic lights) in the model. This is to be used for controlling the traffic controllers in the simulation model.

**Traffic Indicators** is processing the sensor data into traffic indicators which can be used as input for the signal control. Traffic indicators is not needed if only detector data is used as input. When rradar or camera data is used, then the traffic indicators component is needed.

**Clockwork** is a traffic light controller that subscribes to data inputs (e.g. detector statuses) and provides signal contol commands (*Signal Group Control* messages) as an output. It should be noted that this unit can be used both with a simulator as well as with real traffic controllers, given that there is an interface for relaying them to the controller (this part is not provided at the time of writing due to IP restrictions).

**User Interface** is a simple user intraface providing monitoring and limited managemen fore the other services. In essence, this is a web server connectiong to the backend NATS-broker and providing an user interface accessible with a browser.


In order to run the basic system you need to have [docker](https://docs.docker.com/get-started/get-docker/) installed into your system. 

After this you can setup the full Open Controller system and run it with a relatively simple test model by issuing command:

    docker compose up

This script will in essence install four separate docker containers and run them, they are:

- Nats server, a standard [NATS](https://nats.io) message broker
- Clockwork, the open source traffic light controller
- Simengine, a [SUMO](https://eclipse.dev/sumo/) simulation platform with interfaces to access the open controller
- UI, an user interface for the system

After this you should be able to see the user interface via [http://127.0.0.1:8050](http://127.0.0.1:8050)

One should note that the simulation model in this example is ran inside a container without a UI, if you wish to see the intersection in operation, you will need to run the Sumo and simengine in your local computer in the graphical mode. How to do this is explained in [here](#installing-and-running-simengine-in-local-computer)

## Operating the user interface
Likely the first use of the system is to be done via the UI component. When the system is run, one can access it in the localhost port 8050 (i.e. [http://127.0.0.1:8050](http://127.0.0.1:8050)) 

## Monitoring the messages
In order to monitor the messages, you will need a nats-client. Installing this depends on your operating system, and the instructions can be found [here](https://docs.nats.io/running-a-nats-service/clients). It should be noted that the server itself is not needed, since it will be provided in it's own container and accessibles via the standard port in the host. That is, you can subscribe to all the NATS-messages by iussuing a command

    nats sub ">"

One can also subscribe to one or many subjects by replacing ">" with to subject. Wildcards ("*") are also possible. As an example, one can subscribe to all the detector status messages by issuing a command:

    nats sub "detctor.status.*"

Full list of channels are given in the table 1 and a more detailed desctiption of message types and data they contain are given [here](https://www.opencontroller.org/)

*Table 1: The open controller data stream subjects*
| Subject prefix   | Source    | Example                      | Description                           |
| ---------------- | --------- | ---------------------------- | ------------------------------------- |
| detector.status  | simengine | detector.status.1-001        | Status of a deector (occupied or not) |
| group.status     | simengine | group.status.270.1           | Status of a traffic light             |
| radar            | simengine | radar.270.2.objects.json     | Radar object list                     |
| controller       | clockwork | controller.status.270        | Open controller status                |
| group.control    | clockwork | group.control.270.1          | Control message of a traffic light    |

## Installing and running individual components
### Two methods for operating the system

There are two main methods for running and using the Open Controller components: 1) running them in therir own docker containers (this is the method used in the quick start) and 2) running them in your local computer or a server. Both methods have their benefits.

Running the system by using docker is relatively straight forward and makes it easy to deploy into different environments, however, debugginf and developing new features mught be a bit more troublesome. In addition, at least as it stands, the SUMO can only be run in the non graphical mode inside the docker.

Running the components on a local computer (pr a server in a cloud) on the other hand has its own drawbacks. The biggest nuisance is the need to install and configure many different libraries and components. In the following, a short instructions are given for bot mehtods.

It should be noted, that it is possible, and recommended, to use the docker installation as a basis of operations and run in the local computer only the parts needed (e.g. the graphical version of Simclient)

### Operating the Open Controller docker cointainers

The Open Controllers can be operated as any other containers in the system by shutting starting and stopping them by using the Docker user interface. Of course they can be started and stopped from command line as well by issuing commands such as

    # Stopping the Simengine (SUMO) controller
    docker container stop oc_simengine_container

Adn started in similar manner:

    # Startind the Simengine (SUMO) controller
    docker container start oc_simengine_container

This is usefull especially when running only one part of the Open Controller package locally and relying the containers for rest of the package.

### Installing and running components to a local computer

#### Installing and running simengine in local computer

[comment]: <> (Installation to a local machine here)


# Configuration

[comment]: <> (Command line arguments under this also)

## Simulation engine

The simulation engine (simengine for short) is a software component that runs the Sumo traffic simulator, collects data from detectors and sensors 
and generates the messages to the controller through NATS. The simengine can also receive messages which control the traffic signals or vehicles (through V2X).
Instructions for configuration can be found here: [Configuration of the simengine](https://github.com/Open-TLC/open_controller/blob/main/doc/simengine/configuration.md)

## Traffic Indicators

## The Controller (Clockwork)

The traffic signal controller (also referred as the clockwork) can be configured by using the following instructions: 
[Configuration of the controller](https://github.com/Open-TLC/open_controller/blob/main/doc/clockwork/configuration.md)

## User Interface

# Documentation and further reading

[comment]: <> (Links to : sysarch, theory and maybe to something else)

# Links and other material

The [Open Controller web page](https://www.opencontroller.org): 

# License

The sofware is released unde the EUPL-1.2 licence, click [here](https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12) for more details.
