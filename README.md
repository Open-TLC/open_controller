![Open Controller Logo](/src/ui/assets/OC_logo_green_horizontal.jpg)

# About 

This is the main repository of Open Controller, an open source traffic light controller.  **

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

One should note that the simulation model in this example is ran inside a container without a UI, if you wish to see the intersection in operation, you will need to run the Sumo and simengine in your local computer in the graphical mode. How to do this is explained in [here](#installing-and-running-simengine-in-local-computer)


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

In addittion, simclient can also receive *Signal Group control* messsages dictating the statuses of the signal groups (traffic lights) in the model. This is to be used for controlling the traffic controllers in the simulation model.

**Clockwork** is a traffic light controller that subscribes to data inputs (e.g. detector statuses) and provides signal contol commands (*Signal Group Control* messages) as an output. It should be noted that this unit can be used both with a simulator as well as with real traffic controllers, given that there is an interface for relaying them to the controller (this part is not provided at the time of writing due to IP restrictions).

**UI** is a simple user intraface providing monitoring and limited managemen fore the other services. In essence, this is a web server connectiong to the backend NATS-broker and providing an user interface accessible with a browser.


## Operating the user interface
Likely the fist use of the system is to be done via the UI component. When the system is run, one can access it in the localhost port 8050 (i.e. [http://127.0.0.1:8050](http://127.0.0.1:8050)) 

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

## Configuration

[comment]: <> (Command line arguments under this also)

### Simengine

### The Controller (Clockwork)

Clockwork is the core component of the open controller. It takes care of the basic functions of signal group oriented traffic control.
The configuration file of the open controller is a JSON-file, in which the each data type has a header called 'key'. The key can be
a title which defines the data item e.g. the maximum green time 'maxgreen'. The key can also be a given name of a component like signa group e.g. 'group1'.
The structure of the configuration file is so called 'dictionary'. This means that once open controller has read the configuation file,
it can access any data item within the dictionary by setting the the key as input. 

The configuration file consists of general settings like 'operation mode', 'timer' and 'sumo'. The actual controller settings are in the 'controller' part,
which is also a dictionary. Controller has a 'name' like '266' referring to the actual intersection. There is also a 'sumo_name', which refers to the
intersection in the sumo simulator. 

The signal groups are defined as a list of dictionaries:

"group1":{                                         # signal group name
            "min_green": 4,                        # minimum green time
            "min_amber_red": 1,                    # amber red time
            "min_red": 20,                         # minimum red time
            "min_amber": 3,                        # amber time
            "max_green": 30,                       # maximum green time
            "max_amber_red": 1,                    # NA
            "max_red": -1,                         # NA
            "max_amber": 3,                        # NA
            "request_type": "fixed",               # request type options: 'fixed', 'detector'
            "phase_request": false,                # NA
            "green_end": "remain",                 # green end options: 'remain', 'after_max'
            "channel": "group.control.266.1"       # NATS channel to send the commands to the TLC
            },

The next part is defining the detectors, which can be of type 'request' or type 'extender'. 

"req1m20A":{                                      # detector name
            "type": "request",                    # detector type
            "sumo_id": "266_102A",                # sumo name
            "channel": "detector.status.266_102A", # NATS-channel to read the detector status
            "request_groups": ["group1"]         # signal group to be requested
        },

"ext1m20A":{                                     # detector name
            "type": "extender",                  # detector type
            "sumo_id": "266_102A",               # sumo name
            "channel": "detector.status.266_102A", # NATS-channel to read the detector status
            "group": "group1",                   # signal group to be extended
            "ext_time": 2.0                      # extension time
        },

        





#### The basic functions

#### Smart extender
        
#### Priorities

#### Multi-modal traffic

#### Signal coordination

### User Interface


# Documentation and further reading

[comment]: <> (Links to : sysarch, theory and maybe to something else)


    

# License

The sofware is released unde the EUPL-1.2 licence, click [here](https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12) for more details.
