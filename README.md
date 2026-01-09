![Open Controller Logo](/src/ui/assets/OC_logo_green_horizontal.jpg)

# About 

This is the main repository of Open Controller, an open source traffic light controller.  **

# Basic usage

The open controller can be used in several ways. When starting a new project it is recommended to test evarything within simulation. 
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

It should be noted that the options 3 and 4 cannot be used without interface component to the signal controller device. For safety
reasons this component is not publicly open. Only the City of Helsinki can provide access to the real signal controller.


## Using the integrated version

The most simple way of running open controller is so called integrated simulation. In this case, no communication channels are needed
between the controller and simulation, because the the open controller access the simulator using direct commands through Traci-interface.

To run the opne controller in integrated mode, you call the controller in python and give a configuration file name and path as 
command line parameter. See the example below. 

```json
python src/clockwork/clockwork.py --conf-file=models/testmodel/oc_demo_basic.json 
```

The configuration file involves everything needed to run the open controller with Sumo. The Sumo configuration file can
be given within the open controller configuration file or as command line paramter.

The open controller takes a time step (default value = 0.1 sec), reads the detector data from Sumo and updates its own internal states. 
Finally it send the new traffic signal states to the Sumo and continues with next update.
The integrated simulation can be run in real-time or with full speed depending on the available computing power.



## Using the distributed version

### What comes with the package
The open controller system conists of separate services communcating with each other via bub/sum messages (see Figure 1). The messaging broker used in the  implementation is [NATS](https://nats.io) service ran ion it's own docker container and standard port 4222. There are three services, each running in their own container:

- **Simengine**, a sumo simulation environment with Open Controller interfaces
- **Clockwork**, the traffic light controller
- **UI**, an user interface for monitoring and controlling the services

![Open Controller Docker Services](/doc/images/OC_Docker_Services.png)
*Figure 1: Open Controller Standard Services*

**Simengine** is a service for running [SUMO](https://eclipse.dev/sumo/) simulation in real time and providing interface for exchang messages between the Sumo model and other applications and services. The simulation works as a simulated "reality" and provides similar outputs one would be getting from a field devices, namely:

- *Detector statuses* (induction detector determining if there is a vehicle over certain area)
- *Signal Group statuses* (status of traffic lights), and
- *Radar statuses* (object list of vehicles in pre-detemind area)

In addittion, simclient can also receive *Signal Group control* messsages dictating the statuses of the signal groups (traffic lights) in the model. This is to be used for controlling the traffic controllers in the simulation model.

**Clockwork** is a traffic light controller that subscribes to data inputs (e.g. detector statuses) and provides signal contol commands (*Signal Group Control* messages) as an output. It should be noted that this unit can be used both with a simulator as well as with real traffic controllers, given that there is an interface for relaying them to the controller (this part is not provided at the time of writing due to IP restrictions).

**UI** is a simple user intraface providing monitoring and limited managemen fore the other services. In essence, this is a web server connectiong to the backend NATS-broker and providing an user interface accessible with a browser.


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

## Configuration

[comment]: <> (Command line arguments under this also)

### Simengine

### The Controller (Clockwork)

#### Running the Clockwork

The Clockwork can be run outside of the container by giving approapriate command line parameters: 
```json
python src/clockwork/clockwork.py --conf-file=models/testmodel/oc_demo_basic.json --nats-server localhost
```

#### General settings

```json
"timer":{
    "timer_mode": "fixed",
    "time_step":0.1,
    "real_time_multiplier":1
},
"operation_mode":"test",
"v2x_mode": false,
"vis_mode": "main_states",

"nats":{
    "server": "localhost",
    "port": "4222",
    "mode": "change"
},
"sumo":{
    "graph" : true,
    "file_name": "../testmodels/JS_266/cfgFiles/JS_266-267.sumocfg",
    "print_status": true
},
```

#### The basic functions

Clockwork is the core component of the open controller. It takes care of the basic functions of signal group oriented traffic control.
Signal groups tend to green if requested, but other signal groups may prevent it because of conflicting greens, intergreen time or
another conflicting group is first in line to go green. Once the signal group is green and the minimum green time is elapsed then it can start extending the green time based
on detector inputs. If any detector sends an extension signal to the signal group, then the green will be continued until the maximum green time.
The green can end due to no more extension, maximum time reached or other conflicting group orders to go red.
The signal groups states go though a cycle of states described in table x.

*Table 1: Signal group states*
| State | Description |
|-------|-------------|
| 0 | Red/yellow |
| 1 | Minimum green |
| 4 | Remain green (passive green) |
| 5 | Green extended (active green) |
| < | Amber time |
| a | Minimum red |
| b | Red, not requested |
| c | Red requested |
| f | Green permission given, next to go green |
| g | Intergreen time |

The configuration file of the open controller is a JSON-file, in which the each data type has a header called 'key'. The key can be
a title which defines the data item e.g. the maximum green time 'maxgreen'. The key can also be a given name of a component like signa group e.g. 'group1'.
The structure of the configuration file is so called 'dictionary'. This means that once open controller has read the configuation file,
it can access any data item within the dictionary by setting the the key as input. 

The configuration file consists of general settings like 'operation mode', 'timer' and 'sumo'. The actual controller settings are in the 'controller' part,
which is also a dictionary. Controller has a 'name' like '266' referring to the actual intersection. There is also a 'sumo_name', which refers to the
intersection in the sumo simulator. 

The signal groups are defined as a list of dictionaries. The time values are in seconds. The fields not in use are markef with (NA). The order of items within the dictionary does not matter:

*Table 2: Signal group settings*
| Key                                    | Value         | Description                                          |
|----------------------------------------|---------------|------------------------------------------------------|
| "group1"                               | dictionary    | signal group name                                    |
| "min_green"                            | 4             | minimum green time                                   |
| "min_amber_red"                        | 1             | amber red time                                       |
| "min_red"                              | 20            | minimum red time                                     |
| "min_amber"                            | 3             | amber time                                           |
| "max_green"                            | 30            | maximum green time                                   |
| "max_amber_red"                        | 1             | NA                                                   |
| "max_red"                              | -1            | NA                                                   |
| "max_amber"                            | 3             | NA                                                   |
| "request_type"                         | "fixed"       | request type options: 'fixed', 'detector'            |
| "phase_request"                        | false         | NA                                                   |
| "green_end"                            | "remain"      | green end options: 'remain', 'after_ext'             |
| "channel"                              | "group.control.266.1" | NATS channel to send the commands to the TLC |

Example of signal group configuration
```json
"signal_groups":{
        "group1":{
            "min_green": 5,
            "min_amber_red": 1,
            "min_red": 5,
            "min_amber": 3,
            "max_green": 30,
            "max_amber_red": 1,
            "max_red": -1,
            "max_amber": 3,
            "request_type": "detector",
            "phase_request": false,
            "green_end": "remain"
            },
        "group2":{
            "min_green": 8,
            "min_amber_red": 1,
            "min_red": 5,
            "min_amber": 3,
            "max_green": 20,
            "max_amber_red": 1,
            "max_red": -1,
            "max_amber": 3,
            "request_type": "fixed",
            "phase_request": false,
            "green_end": "after_ext"
            }
     }
```
The detectors can be of type 'request' or type 'extender'. Requesting detector sends a request signal to the predefined signal groups. 
The requested group can go green if there is no active conflicting green ongoing. If there are only passive greens ongoing,
they will be terminated and the requested group can go green after intergreen period. 

 *Table 3: Request detector settings*
| Key                                    | Value         | Description                                          |
|----------------------------------------|---------------|------------------------------------------------------|
| "req1m20A"                             | dictionary    | detector name                                        |
| "type"                                 | "request"     | detector type                                        |
| "sumo_id"                              | "266_102A"    | amber red time                                       |
| "request_groups"                       | ["group1"]    | a list of signal groups to be requested              |
| "channel"                              | "detector.status.266_102A"| NATS-channel to read the detector status |

Detector of type "extender" can extend an ongoing green signal keeping it in active state, which normally cannot be
terminated by other signal groups. Each vehicle passing the detector will extend the green time with predefined time (ext_time).
This means that if the gap between successive vehicles is more the the "ext_time" then the green time is no more extended.
It should be noted that time of detector being occupied is not counted, but the extension time starts from the trailing edge of the detector pulse.
An occupied detector always extends regardless of the time. 

 *Table 4: Extension detector settings*
| Key                                    | Value         | Description                                          |
|----------------------------------------|---------------|------------------------------------------------------|
| "ext1m20A"                             | dictionary    | detector name                                        |
| "type"                                 | "extender"    | detector type                                        |
| "sumo_id"                              | "266_102A"    | amber red time                                       |
| "group"                                | "group1"      | signal group to be extended                          |
| "ext_time"                             | 2.0           | extension time                                       |
| "channel"                              | "detector.status.266_102A"| NATS-channel to read the detector status |

Example of detector section in the configuration file
```json
"detectors":{
        "req1m20A":{
            "type": "request",
            "sumo_id": "266_102A",
            "channel": "detector.status.266_102A",
            "request_groups": ["group1"]
        },
        "ext1m20A":{
            "type": "extender",
            "sumo_id": "266_102A",
            "channel": "detector.status.266_102A",
            "group": "group1",
            "ext_time": 2.0
        }
  }
```

After defining the signal groups and their parameters the user should list the groups that are actually used in the control. 
User may define groups that are not currently used and activate them by adding to the list. It is important that the number
of signal groups in the group_list matches with number of groups in the intergreen matrix and the in the phase ring definition.

Example of the group list:
```json
"group_list": ["group1", "group2", "group3", "group4", "group5", "group6", "group7", "group8", "group9", "group10", "group11", "group12", "group13", "group14", "group15"],
```

An intergreen matrix is defined to secure enough safety time between end and start of conflicting green signals. The intergreen times
are very case specific depending on intersection geometry etc. Therefore each pair of conflicting greens have
to be defined in the integreen matrix. The matrix is not symmetric, since for example when pedestrian signal is ending,
then very long intergreen is needed to guarantee each pedestrian enough time to pass the street. However, the other way round,
if car signal is ending, then pedestrian green can be started almost immediately. In table X, the starting signal groups
has to to check all integreen times in its column and use the maximum value. 

Example of the intergreen matrix. Rows refer to ending groups and columns to starting groups.
```json
   "intergreens":[  [0.0, 0.0, 0.0, 0.0, 5.0, 7.0, 6.0, 6.0, 6.0, 4.0, 4.0, 0.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 8.0, 0.0, 0.0, 4.0, 8.0, 8.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0, 9.0, 0.0, 8.0, 9.0, 8.0, 1.0, 5.0, 1.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0, 8.0, 0.0, 7.0, 4.0, 0.0, 6.0, 10 , 6.0, 0.0, 0.0, 0.0],
                    [7.0, 0.0, 5.0, 5.0, 0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 4.0, 8.0, 8.0],
                    [5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 4.5, 4.5, 0.5],
                    [6.0, 8.0, 8.0, 7.0, 7.0, 0.0, 0.0, 6.0, 6.0, 0.0, 0.0, 0.0, 4.5, 4.5, 0.5],
                    [8.0, 8.0, 0.0, 4.0, 0.0, 0.0, 8.0, 0.0, 0.0, 0.0, 0.0, 0.0, 6.0, 10 , 6.0],
                    [7.0, 0.0, 7.0, 0.0, 0.0, 0.0, 7.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 5.0, 1.0],
                    [5.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    [5.0, 4.0, 5.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    [1.0, 4.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0, 1.0, 9.0, 9.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0, 2.0, 6.0, 6.0, 5.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0, 5.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                 ] 
```
In signal group control, there are no fixed phases. Basically any non-conflicting group could start the green.
However, there should be a mechanism to put competing conflicting green requests in order. A phase ring is used
to decide which signal group get green first, if there are conflicting green requests. The phase ring does not
provide fixed stages, but it defines in which order green permits are given.

Example of the phase ring. Number 1 means green permission can be given in the phase.
```json
   "phases":[  [0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0 ],
               [1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1 ],
               [0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 1 ,1, 0, 0, 0 ]
            ]
```

#### Smart extender

Smart extender can be used instead of the extending detectors. The smart extender is not using the detector input,
but uses more holistic scene understanding based on radar and camera data. The data for smart extender is provided
by the traffic indicators component which is running independently from the open controller. The traffic indicators
is processing the raw sensor data and providing meaningful indicators as input to the smart extenders. 

The smart extender relies basically on two main inputs. It is looking at the approaching vehicles on the lanes it is
controlling. The number of approaching vehicles (APPR) is the basic input. However, as the smart extender get a list of
approaching vehicles with their type, speed etc. information, it can give different weigths for example based on
vehicle type (e.g. 1 truck equals 3 passenger cars). 

Unlike the extending detector, the smart extender is looking at the traffic situation behind the conflicting signal groups.
The basic input is the sum of all vehicles (in queue or not) behind the conflicting signal groups. 

The decision about green extension is made per each update of the open controller ca. 10 times per second. The smart extender
looks at the APPR and CONFQUEUE values and calculates their ratio APPR/CONFQUEUE. When this value gets lower than a given
theshold, then the green extension is terminated. The EXT_THRESHOLD is a parameter in the smart extender settings.
After the extension the signal can remain in passive green or go to red just like with extending detectors.

To avoid overly long green extensions, there has to be a mechanism to make the green extension harder over time. Therefore,
the EXT_THRESHOLD-value is increased based on how long the green signal has been active. By increasing the EXT_THRESHOLD, the termination
of the extension get more likely and eventually getting so high that the extension must end. The parameters used here
is called TIME_DISCOUNT. 

User can always set a hard maximum time to the signal group, which overrules any attemps to extend the green. 
Also the minimum green time is always guaranteeed despite of any other timing settings.

Configuration of the smart extender consists of two blocks in the open controller configuration file. Firstly,
the a special detector type is defined. There are two main detector types defined in open controller namely type "e1"
and type "e3". The naming convention comes from the Sumo traffic simulator which uses the same type. Detector of
type "e1" is the "normal" occupancy detector, which has only states "true" or "false". The "e3" detector represents
a radar input since it defines an area in which vehicles are detected and tracked. The output of the "e3" detector
is a list of vehicles with some optional features likes vehicle type and speed. 
The configuration of e3-detector is described below.

 *Table 5: Extension detector settings*
| Key                                    | Value         | Description                                          |
|----------------------------------------|---------------|------------------------------------------------------|
| "e3d2m80"                              | dictionary    | detector name                                        |
| "type"                                 | "e3detector"  | detector type                                        |
| "sumo_id"                              | "e3Det_266_Mech_Left"   | name in Sumo simulation                    |
| "group"                                | "group1"   | signal group to be extended                             |
| "channel"                              | "group.e3.266.2" | NATS-channel to read the traffic indicators       |

Example of smart extender detector configuration
```json
"e3g2m80":{
        "type": "e3detector",
        "sumo_id": "e3Det_266_Mech_Left",
        "channel": "group.e3.266.2",
        "group": "group2"
        },
```
The "e3" detector has a name, which is the key value of the following dictionary including the parameters. User can
select the name freely. Here the g2 refers to signal group 2 and m80 to the range of 80 meters of detecting area. 
In the Sumo-simulator the e3-detectors must be added to the network. In live operation, the actual radars define
the area of detection.

The smart extender has two main parameters for its operation. The default value for EXT_THRESHOLD is 0.25 and for
TIME_DISCOUNT 60. If the user doesn't need to change the default values, then no extra settings is needed. 
However, if the user want to edit the paramters, then "extender" section needs to be defined. 

Example of smart extender parameter settings
```json
"extenders":{
        "ext1": {
            "group": "group1",
            "ext_mode": 4,
            "ext_threshold": 0.25,
            "time_discount": 60 
            }
    }
```

#### Priorities

Priorities can be implemented in two ways. If open controller is used without the smart extenders i.e. by using
the normal detectors as the only input, then priority is defined within the detectors. The request set up by a
detector can have a priority level input. If not defined, the default priority level is 2 for normal car traffic. 
If the request level of the detector is higher, e.g. to 5, then this request can cut off an active green with priority level 2. 
An active green with higher priority level cannot be cut another request of same or lower priority level. 
In practice the higher priority levels are given to public transport like trams only. However, in principle, it is
possible to prioritize any other mode of traffic or any given approach. 

The alternative approach is to use the smmart extender for priorities, too. This is done by configuring the smart
extender so, that it will give extra weight to a given vehicles type like tram. If a tram is regognized, then the
predefined weight is associated with the vehicle. For example, if a weight 100 is configured to thr tram, then the
open controller thinks that there is 100 passenger cars approaching or in a queue. This means the that the tram
approach can easily cut conflicting active greens to starts it own green earlier. Also, as soon as started, the
green with weight 100 is not likely to be cut by any other approaches, even if the tram is still waiting on station.
As soon as the tram has passed ist own signasl then the extension end and othe approaches may get green if requested. 

#### Multi-modal traffic

The traffic in intersections consists of vehicles like car, trucks, buses and trams. Hoever, the pedestrians, bicycles
and micro-mobility is often negleted in many ways. Pedestrians and bikers are not detected automatically like vehicles,
which can be annoying espcially for cyclists. Also, the signal timing is not affected by the pedestrian counts. 

Having the the radars and espcially the cameras we can detect the pedestrians automatically and generate the requests.
Also, it is possible to get the count of pedestrians waiting for green and give them extra weight in order to get the
green earlier. While crossing the street, we can count the pedestrians and extend the green time is necessary. 

#### Signal coordination

Traffic signal coordination is used when certain routes over multiple intersections need to be favored. 
Traditionally this is done by using common cycle time for all the intersections and the green starting
at consecutive intersections are staggered to create a green wave. In open controller the signal coordination
is implemented if different manner (at least so far). By default each intersection runs in isolated mode
using the smart extenders. Then the prioritized lanes on prioritized routes are given extra  weight. 
This weight can either cut the conflicting green to start thee green when needed or to extend the the
ongoing green. The difference to the isolated mode is that the request to start green or to extend the 
green can come from previous intersections. One signal head can have multiple smart extenders and the
in coordination the prioritized signal groups have extra extenders from the previous intersections.



### User Interface


# Documentation and further reading

[comment]: <> (Links to : sysarch, theory and maybe to something else)


    

# License

The sofware is released unde the EUPL-1.2 licence, click [here](https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12) for more details.
