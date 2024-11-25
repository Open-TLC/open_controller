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

- Simclient, a sumo simulation environment with Open Controller interfaces
- Clockwork, the traffic light controller
- UI, an user interface for monitoring and controlling the services

![Open Controller Docker Services](/doc/images/OC_Docker_Services.png)
*Figure 1: Open Controller Standard Services*


[comment]: <> (System description)

## Installation

[comment]: <> (Installation to a local machine here)

## Running separate components

[comment]: <> ( 1.  Docker and 2. local)

## Configuration

[comment]: <> (Command line arguments under this also)

### Simengine

### The Controller (Clockwork)

### User Interface


# Documentation and further reading

[comment]: <> (Links to : sysarch, theory and maybe to something else)


    

# License

The sofware is released unde the EUPL-1.2 licence, click [here](https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12) for more details.
