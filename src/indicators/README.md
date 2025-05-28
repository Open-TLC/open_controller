![Open Controller Logo](/src/ui/assets/OC_logo_green_horizontal.jpg)

# Overview

This module provides a microservice for calculating traffic indicators, defined as quantitative representations of traffic conditions. These indicators support efficient and safe signal control, specifically:

- Requests for green phases at specific intersections
- Queue lengths and vehicle counts by approach
- Timing thresholds for terminating green phases

The Traffic Indicators component is primarily intended to operate as part of a traffic management system, transforming raw input data into meaningful values for a controller, as shown in the diagram below.

![Traffic_indicators-Open Controller.drawio-3.svg](/doc/images/IND_overview.svg)

Although primarily designed to feed Open Controller, the component is implemented as a standalone service. It can operate independently to provide traffic data to other systems.

# Getting started

## Prerequisites

To run the service, you need a working NATS server. While Open Controller includes one by default, standalone instructions are available on the [NATS website](https://nats.io/).

Meaningful operation also requires input data. You can simulate input using a SUMO model. Instructions are available at [XXX].

Note: These instructions have been tested on macOS 15.5 (Sequoia) but should apply across most Unix-like environments.

## Running with docker

- This will include docker and non docker use

## Running Natively

To run the component without Docker, ensure a compatible Python 3.x installation (version XX or newer is recommended). Required dependencies include `nats-py`; a full list can be found in the Docker installation section [XXX].

Launch the system using:

```
python src/indicators/traffic_indicators.py
```

# Data Interface

## Overview

All input and output data are structured as JSON messages and exchanged via a NATS message broker. This section outlines all supported data types with examples.

## Input Types

[To be filled in: Detailed data format examples]

## Output Types

[To be filled in: Detailed data format examples]

# Configuration

## **Overview**

Component behavior is defined by a JSON configuration file that specifies inputs, outputs, and their interconnections. This section covers:

- Input and connection structure
- Field of View (FoV) outputs
- 

## Inputs and connectivity

The configuration defines input and output behaviors through the following sections:

| Section | Purpose | Notes |
| --- | --- | --- |
| connectivity | Declares data source details | Currently NATS only |
| input_streams | Specifies subscribed data streams |  |
| inputs | Declares fields used for fusion | Feeds the fusion inference logic |

These sections are interdependent: `inputs` rely on `input_streams` to access message streams, which in turn connect to physical sources via the `connectivity` block. This relationship is illustrated below:

![Traffic_indicators-Input Configuration.drawio.svg](/doc/images/IND_inputs.svg)

Example configuration snippet:

```json
{
"connectivity":{
    "notes": "This is for accessing the data",
    "nats": {
        "server": "localhost",
        "port": 4222
    }
},

"input_streams":{
    "sig_inputs": {
        "connection": "nats",
        "type": "groups",
        "subtype": "sumo",
        "nats_subject": "group.status.270.*",
        "notes": "Will subscribe to all groups sent by sumo"
    },
    "det_inputs": {
        "connection": "nats",
        "type": "detectors",
        "subtype": "sumo",
        "nats_subject": "detector.status.*",
        "notes": "Will subscribe to all detectors sent by sumo"
        },    
    "radar270.1": {
        "connection": "nats",
        "type": "radar",
        "subtype": "sumo",
        "nats_subject": "radar.270.1.objects_port.json",
        "notes": "Will subscribe to radar pointing north"
        }
    },

"inputs":{
    "dets":{
        "2-002": {
            "type": "falling_edge",
            "stream": "det_inputs",
            "name": "2-002"
        },
        "2-040": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "2-040"
        }

    },
    "rad_lanes":{
        "270_1_0": {
            "type": "simple",
            "stream": "radar270.1",
            "lane": "0"
        }
    },
    "groups": {
        "group2": {
            "type": "simple",
            "stream": "sig_inputs",
            "group": "2"
        }
    }
},
```

## Field of view output

The Field of View (FoV) output is the primary data product consumed by the Open Controller. It estimates how much traffic is governed by a specific signal group—both incoming road users (pedestrians, cyclists, vehicles) approaching a green light and those queuing behind a red light.

The FoV inspects the traffic in pre-detemined lanes (that is the ones controlled by the given signal group) and thus knows all relevant traffic flows approaching it, given that it knows about all the road users on those lanes. The sections defined in FoW output are (note that data inputs described above are needed as well):

| Section | Use | Notes |
| --- | --- | --- |
| lanes | A lane is logial approach unit matching relevant areas of radar coverage as well as input and output detectors | One or many lanes constitute FoW |
| outuputs | defines the relevant lanes as well as output types and triggering options |  |

Current set up uses two data types for determining the road users approaching: 1) loop detectors, that count vehicles passing them, and 2) radars detecting all vehicles within its beam. These data sources are mapped into “input detectors” and “ouptupd detectors” for each lane (that is: we count all the vehicles entering the lane and all the vehicles exiting it) as well as filtering out the relevant lanes from the list of road users provided by the radar. How these thins are connected is illustrated in the following diagram:

![Traffic_indicators-FOW Configuration.drawio-2.svg](/doc/images/IND_FoV.svg)

We are not explaining the details of the algorithms operating in the calculation (for more details, see: XXX), however, it should be noted that these connections are reflected in the configuration. The field of view is determined as an output, and it is mapped to a lista of lanes and one signal group. Each lane is  then connected to a list of input detectors, list of output detectors as well as list of lanes detected by a radar. A simple example with one input detector, one ouptut detector and one “radar lane” looks like following:

```json
"lanes":{
    "grp2_1":{
        "name": "Group 2 lane 1",
        "in_dets": ["2-040"],
        "out_dets": ["2-002"],
        "radar_lanes":["270_1_0"],
        "notes": "Approach from north"
    }
},

"outputs":{   
    "group2_view":{
        "connection": "nats",
        "type": "e3",
        "nats_output_subject": "group.e3.270.2",
        "trigger": "time",
        "trigger_time": 1.0,
        "lanes": ["grp2_1"],
        "group": "group2",
        "detectors_broken": false, 
        "notes": "An example"
        }
    }
}
```

It should be noted that the actuar detectors, radar_lanes and signal groups have to be defined in the configuration. These definitions are explained in the previous chapters.

## Configuration file example

The full configuration file used in this example is:

```json
{
"connectivity":{
    "notes": "This is for accessing the data",
    "nats": {
        "server": "localhost",
        "port": 4222
    }
},

"input_streams":{
    "sig_inputs": {
        "connection": "nats",
        "type": "groups",
        "subtype": "sumo",
        "nats_subject": "group.status.270.*",
        "notes": "Will subscribe to all groups sent by sumo"
    },
    "det_inputs": {
        "connection": "nats",
        "type": "detectors",
        "subtype": "sumo",
        "nats_subject": "detector.status.*",
        "notes": "Will subscribe to all detectors sent by sumo"
        },    
    "radar270.1": {
        "connection": "nats",
        "type": "radar",
        "subtype": "sumo",
        "nats_subject": "radar.270.1.objects_port.json",
        "notes": "Will subscribe to radar pointing north"
        }
    },

"inputs":{
    "dets":{
        "2-002": {
            "type": "falling_edge",
            "stream": "det_inputs",
            "name": "2-002"
        },
        "2-040": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "2-040"
        }

    },
    "rad_lanes":{
        "270_1_0": {
            "type": "simple",
            "stream": "radar270.1",
            "lane": "0"
        }
    },
    "groups": {
        "group2": {
            "type": "simple",
            "stream": "sig_inputs",
            "group": "2"
        }
    }
},

"lanes":{
    "grp2_1":{
        "name": "Group 2 lane 1",
        "in_dets": ["2-040"],
        "out_dets": ["2-002"],
        "radar_lanes":["270_1_0"],
        "notes": "Approach from north"
    }
},

"outputs":{   
    "group2_view":{
        "connection": "nats",
        "type": "e3",
        "nats_output_subject": "group.e3.270.2",
        "trigger": "time",
        "trigger_time": 1.0,
        "lanes": ["grp2_1"],
        "group": "group2",
        "detectors_broken": false, 
        "notes": "An example"
        }
    }
}
```


