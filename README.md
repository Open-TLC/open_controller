![Open Controller Logo](https://github.com/Open-TLC/open_controller/blob/main/ui/assets/OC_logo_green_horizontal.jpg)

# About 

This is the main repository of Open Controller, an open source traffic light controller.

# Quickstart

In order to run the basic system you need to have [docker](https://docs.docker.com/get-started/get-docker/) installed into your system. 

After this you can setup the full Open Controller system and run it with a relatively simple test model by issuing command:

    docker compose up

This script will in essence install four separate docker containers and run them, they are:

- Nats server, a standard [NATS](https://nats.io) message broker
- Clockwork, the open source traffic light controller
- Simengine, a [SUMO](https://eclipse.dev/sumo/) simulation platform with interfaces to access the open controller
- UI, an user interface for the system

After this you should be able to see the user interface via [http://127.0.0.1:8050](http://127.0.0.1:8050)

[comment]: <> (Reference to use with graphical ui here)

# Basic usage
## What comes with the package
The open controller system conists of separate services communcating with each other via bub/sum messages (see Figure 1). The messaging broker used in the  implementation is [NATS](https://nats.io) service ran ion it's own docker container and standard port 4222. There are three services, each running in their own container:

- **Simclient**, a sumo simulation environment with Open Controller interfaces
- **Clockwork**, the traffic light controller
- **UI**, an user interface for monitoring and controlling the services

![Open Controller Docker Services](/doc/images/OC_Docker_Services.png)
*Figure 1: Open Controller Standard Services*

**Simclient** is a service for running [SUMO](https://eclipse.dev/sumo/) simulation in real time and providing interface for exchang messages between the Sumo model and other applications and services. The simulation works as a simulated "reality" and provides similar outputs one would be getting from a field devices, namely:

- *Detector statuses* (induction detector determining if there is a vehicle over certain area)
- *Signal Group statuses* (status of traffic lights), and
- *Radar statuses* (object list of vehicles in pre-detemind area)

In addittion, **simclient** can also receive *Signal Group control* messsages dictating the statuses of the signal groups (traffic lights) in the model. This is to be used for controlling the traffic controllers in the simulation model.

**Clockwork** is a traffic light controller that subscribes to data inputs (e.g. detector statuses) and provides signal contol commands (*Signal Group Control* messages) as an output. It should be noted that this unit can be used both with a simulator as well as with real traffic controllers, given that there is an interface for relaying them to the controller (this part is not provided at the time of writing due to IP restrictions).

**UI** is a simple user intraface providing monitoring and limited managemen fore the other services. In essence, this is a web server connectiong to the backend NATS-broker and providing an user interface accessible with a browser.


## Operaing the user interface


## Monitoring the messages


## Installing and running individual components
### Two methods for operating the system
There are two main methods for running and using the Open Controller components: 1) running them in therir own docker containers (this is the method used in the quick start) and 2) running them in your local computer or a server. Both methods have their benefits.

Running the system by using docker is relatively straight forward and makes it easy to deploy into different environments, however, debugginf and developing new features mught be a bit more troublesome. In addition, at least as it stands, the SUMO can only be run in the non graphical mode inside the docker.

Running the components on a local computer (pr a server in a cloud) on the other hand has its own drawbacks. The biggest nuisance is the need to install and configure many different libraries and components. In the following, a short instructions are given for bot mehtods.

It shoule be noted, that it is possible, and recommended, to use the docker installation as a basis of operations and run in the local computer only the parts needed (e.g. the graphical version of Simclient)

### Operating the Open Controller docker cointainers

### Installing components to a local computer

[comment]: <> (Installation to a local machine here)

## Configuration

[comment]: <> (Command line arguments under this also)

### Simengine

### The Controller (Clockwork)

### User Interface


# Documentation and further reading

[comment]: <> (Links to : sysarch, theory and maybe to something else)


    

# License

The sofware is released unde the EUPL-1.2 licence, click [here](https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12) for more details.
