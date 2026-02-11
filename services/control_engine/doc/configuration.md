# Traffic controller configuration

The configuration of the controller is defined by a json-file, which consists of several blocks.
In the beginning there are general sections like "timer", "operation_mode" and "sumo". These 
sections are obligatory so that the controller doesn't run without them.
There can be additional voluntary sections which are explained later. 

The next section is called 'controller', which consist of subsections like: 
"signal_groups", "detectors", "extenders", "phases" and "intergreens". 
The controller has a name, which user can select freely. There is also "sumo_name", which
has to match with the controller name in the sumo-configuration file.
In the example below, not all items withing the sections are shown to keep the file short.

```json
{
    "timer":{
        "timer_mode": "fixed",
        "time_step":0.1,
        "real_time_multiplier":1,
        "max_time": 4000
    },

"operation_mode":"test",

"sumo":{
    "graph" : true,
    "file_name": "../testmodels/test.sumocfg",
    "print_status": true,
        "group_outputs": ["group1", "group2", "group3", "group4"]
},

"controller":{
    "name": "test",
    "sumo_name": "N_J1",

    "signal_groups":{

        "group1":{
            "min_green": 4,
            "min_amber_red": 1,
            "min_red": 5,
            "min_amber": 3,
            "max_green": 1000,
            "max_amber_red": 1,
            "max_red": -1,
            "max_amber": 3,
            "request_type": "detector",
            "phase_request": false,
            "green_end": "remain"
            }
        },

    "detectors":{
        
        "req1A":{
            "type": "request",
            "sumo_id": "e1_West1",
            "request_groups": ["group1"]
            }
       
        "e3d1m60":{
            "type": "e3detector",
            "sumo_id": "e3Det_West",
            "group": "group1"
            },              
    },
    
    "extenders":{

        "ext1": {
            "group": "group1",
            "ext_mode": 4,
            "ext_threshold": 0.25,
            "time_discount": 60 
            }

    },
    
    "group_list": ["group1", "group2", "group3","group4"],

    "phases":[
        [1, 1, 0, 0],
        [0, 0, 1, 1]
        ],

    "intergreens":[
        [0.0, 0.0, 3.0, 3.0],
        [0.0, 0.0, 3.0, 3.0],
        [3.0, 3.0, 0.0, 0.0],
        [3.0, 3.0, 0.0, 0.0]
        ]
   
    }
}

```

## General settings

General settings are related to the controller and simulation as a whole. They involve setting various features on and off.

Example of general settings
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
    "file_name": "../testmodels/demo.sumocfg",
    "print_status": true
},
```
Timer is controlling the speed of the simulation and controller. 
If the "timer_mode" is "fixed" then the simulation is run as fast as possible, but if the mode is "real" the the simulation proceed with speed of the "normal" time.
The "time_step" is given in seconds (default value 0.1 seconds). The "real_time_multiplier" can be used speed up the simulation by a given factor for example 2.

*Table X: Timer settings*
| Key | Value |
|-------|-------------|
| "timer_mode" | "fixed" / "real" |
| "time_step" | in seconds |
| "real_time_multiplier" | x times faster than real-time|

Sumo is the simulator started by the Open Controller. A correct path and file name must be given to run the Open Controller.
If the "graph_mode" is "true", then the simulation is visualized on the screen. If the "print_status" is "true" then status information is
printed on the screen including data like time, signal states, request status, extension status etc.

*Table X: Sumo settings*
| Key | Value | Comment |
|-------|-------------|----------------------------------------------|
| "graph" | "true" / "false" | Graphics visualization on/off |
| "file_name" | "../testmodels/demo.sumocfg" | path and file name to the Sumo-configuration file (.sumocfg) |
| "print_status" | "true" / "false" | Printing to console on/off |

NATS is a server which provides communication services between various software components based on publish and subscribe principle.
The "server" defines the IP-address of the NATS-server ("localhost" means that the server is in the local computer).
The messages can be sent based on changes in the status or per each update.

*Table X: NATS settings*
| Key | Value | Comment |
|-------|-------------|----------------------------------------------|
| "server" | "10.8.0.36" / "localhost" | The address of the NATS-server |
| "port" | "4222" | Port number |
| "mode" | "change" / "update" | Sending the data per every update or only when there is a change in status |

Other general setting involve for example the operation mode. This feature is currently used for testing only (="test"),
in which case there can be some functionalities, which are currently testing phase. The "V2X_mode" is "true" then special
features related to the safety green extension through the V2X-communication is set on. The "vis_mode" is used to visualize the
internal states of the traffic signals by coloring the vehicles controlled by the signal based on the signal state. 

*Table X: Other settings*
| Key | Value | Comment |
|-------|-------------|----------------------------------------------|
| "operation_mode" | "test" | This feature is currently not in use |
| "v2x_mode" | "true" / "false" | Setting on/off the safety extension through the V2X |
| "vis_mode" | "off" / "main_states" / "sub_states" | Visualizing the signal states by color of the controlled vehicles |


## The basic functions

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

## Smart extender

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

## Priorities

Priorities can be implemented in two ways. If open controller is used without the smart extenders i.e. by using
the normal detectors as the only input, then priority is defined within the detectors. The request set up by a
detector can have a priority level input. If not defined, the default priority level is 2 for normal car traffic. 
If the request level of the detector is higher, e.g. to 5, then this request can cut off an active green with priority level 2. 
An active green with higher priority level cannot be cut another request of same or lower priority level. 
In practice the higher priority levels are given to public transport like trams only. However, in principle, it is
possible to prioritize any other mode of traffic or any given approach. 

The alternative approach is to use the smart extender for priorities, too. This is done by configuring the smart
extender so, that it will give extra weight to a given vehicles type like tram. If a tram is regognized, then the
predefined weight is associated with the vehicle. For example, if a weight 100 is configured to thr tram, then the
open controller thinks that there is 100 passenger cars approaching or in a queue. This means the that the tram
approach can easily cut conflicting active greens to starts it own green earlier. Also, as soon as started, the
green with weight 100 is not likely to be cut by any other approaches, even if the tram is still waiting on station.
As soon as the tram has passed ist own signasl then the extension end and othe approaches may get green if requested.

Example of configurating priority for trams by smart extender
```json
 "e3_tram_north":{
              "type": "e3detector",
              "sumo_id": "e3det_tram_north",
              "group": "group1",
              "vtypes": ["tram_type"],
              "weight": 100
            },
```

## Multi-modal traffic

The traffic in intersections consists of vehicles like car, trucks, buses and trams. Hoever, the pedestrians, bicycles
and micro-mobility is often negleted in many ways. Pedestrians and bikers are not detected automatically like vehicles,
which can be annoying espcially for cyclists. Also, the signal timing is not affected by the pedestrian counts. 

Having the the radars and espcially the cameras we can detect the pedestrians automatically and generate the requests.
Also, it is possible to get the count of pedestrians waiting for green and give them extra weight in order to get the
green earlier. While crossing the street, we can count the pedestrians and extend the green time is necessary. 

## Signal coordination

Traffic signal coordination is used when certain routes over multiple intersections need to be favored. 
Traditionally this is done by using common cycle time for all the intersections and the green starting
at consecutive intersections are staggered to create a green wave. In open controller the signal coordination
is implemented if different manner (at least so far). By default each intersection runs in isolated mode
using the smart extenders. Then the prioritized lanes on prioritized routes are given extra  weight. 
This weight can either cut the conflicting green to start thee green when needed or to extend the the
ongoing green. The difference to the isolated mode is that the request to start green or to extend the 
green can come from previous intersections. One signal head can have multiple smart extenders and the
in coordination the prioritized signal groups have extra extenders from the previous intersections.



