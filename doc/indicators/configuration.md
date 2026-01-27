# Traffic indicator configuration

## About

This document explains configuring the traffic indicators component, which is part of the [Open Controller](../../../README.md) software package. For usage of this component, see [Traffic indicators overview](./overview.md).


Traffic indicators is a micro service that takes input variables (pre processed data from the traffic environment) and calculates relevant traffic indicators (situational awareness) from it. All inputs and outputs are JSON messages and they are relayed using NATS message broker, as indicated in the following image.

![Traffic Indicators data flows](TI_data_flows.png)

This document describes how the traffic indicators micro service is configured. Conceptually, configuration is based on configuring different output types and their parameters. These are explained in the following chapter. Below the output configuration we provide detailed description of a configuration file and its sections.

This document is divided into three parts: 1) Instructions on how to configure typical outputs ([Output types and configuration](#output-types-and-configuration)), 2) Configuration file reference guide ([Configuration file](#configuration-file)), and 3) Example configuration file ([Example file](#example-file)).

## Output types and configuration
### Traffic indicator outputs

As it stands, traffic indicators provides only one type of an output: Traffic View (this is roughly similar to "e3" detector in Sumo). Following subsection explains configuration of this output type.

### Traffic view 
#### Traffic view and it's idea

Traffic view is an indicator output that tries to estimate vehicles approaching a given traffic signal. One can think of it as a view the traffic signal "sees" when determining when to change its state. This can seem like a relatively limited understanding of traffic conditions, but it has proven to be quite versatile: sophisticated traffic controller schemes can be built by using several views as control inputs. For more information about the corresponding controller configuration, see [Control Engine configuration](../clockwork/configuration).

Configuring the view output can be seen as a data pipeline that starts from the input stream and produces a stream of output messages based on configuration and input data. This process is depicted in the figure below. There are four main steps in this process: 1) **reading the input data** from streams we have configured, 2) **filtering the data** and picking _relevant_ inputs to be used in the state estimation, 3) **estimating the relevant output variables** (i.e., lists of road users) based on input data and the configuration, and 4) **sending the indicator output** to a channel defined in the configuration.

![Traffic View configuration](TI_traffic_view.png)

In terms of configuring, these steps are carried out by configuring the 1) input streams, 2) defining input data, 3) defining traffic lanes, and 4) using one or several lanes to aggregate them into an output.

#### Configuring the streams
The streams are defined in the `input_streams` section of the configuration file. In the example shown in the figure above, we utilize three different input types to calculate the output: 1) detector statuses from specified channels, 2) signal statuses from the controller, and 3) object lists from sensors or other data sources (e.g., radars). They can be configured as follows:

```json
{
    "det_inputs": {
        "connection": "nats",
        "type": "detectors",
        "subtype": "sumo",
        "nats_subject": "detector.status.*",
        "notes": "Detector statuses"
    },
    "sig_inputs": {
        "connection": "nats",
        "type": "groups",
        "subtype": "sumo",
        "nats_subject": "group.status.270.*",
        "notes": "Signal group statuses"
    },
    "radar270": {
        "connection": "nats",
        "type": "radar",
        "subtype": "sumo",
        "nats_subject": "radar.270.1.objects_port.json",
        "notes": "Object lists from radar"
    }
}
```

Each of these streams is subscribed to at the start of the traffic indicators operations, and data is processed as it arrives. In this case, the `connection` for all inputs is NATS, and three different types of data are used (`detectors`, `groups`, and `radar`), with a `nats_subject` defined for each. As illustrated in the example, the object list (`radar270`) of type `radar` is subscribed from one topic (`radar.270.1.objects_port.json`), while detectors and groups subscribe to multiple channels (indicated by the asterisk at the end of the `nats_subject`). Note that the parameters `subtype` and `notes` do not impact the operation; they are included for clarity and future expansion.

The types of streams are as follows:
- **Detector statuses** (`det_inputs`) are messages indicating whether a given detector is "occupied" or "not occupied." In practice, these are typically loop detectors installed beneath the pavement, indicating if a vehicle is present. This type of data can be used to estimate traffic flow (vehicle counts) crossing a section of the road.
- **Signal group statuses** (`sig_inputs`) are streams of messages indicating whether a given signal (or signal group) is green or red, as well as the internal state of the traffic controller. This information can be utilized when estimating traffic conditions.
- **Object lists** (`radar`) are streams of detected objects from sensors such as radars or cameras. Each object typically includes position, velocity, classification, and other attributes. This type of data can be used to estimate vehicle presence and movement in specific traffic lanes.

Streams themselves are not enough for practical operations. Thus the next step in the configuration is to define the indicator inputs.

#### Configuring the inputs
Three types of indicator inputs are defined, each of them corresponding to an input stream. This part of the configuration is best understood as a filter: we take input stream(s) of data and filter relevant inputs from it. In addition to the stream name, each input is given a tag (to be used later) and parameters for the filtering.

In essence, we define inputs by giving them filtering criteria and possible other parameters. Each of these inputs is given a tag that is used later when we define input connections to lanes. The input types and parameters are as follows:

| Input Type | Stream | Filtering Criteria | Other Parameters |
|------------|--------|-------------------|------------------|
| Signal groups (`groups`) | `groups` type stream | Signal group id | - |
| Detectors (`dets`) | `detectors` type stream | detector id, `name`; vehicle type, `vtype` (optional) | trigger type (rising edge, falling edge, change)|
| Object filters (`object_filters`) | `radar` type stream | Lane number | - |

For more details of configuration format see [Inputs and streams](#inputs-and-streams)

#### Configuring the lanes
Lanes are where the actual data fusion happens. Each lane can be configured to: 1) input detectors, 2) output detectors, and 3) one or many filtered object lists.

Lane objects attempt to estimate, how many and what road users there are at any given moment in a given lane (lane can also be a traffic island for example, conceptially we want an area controlled by a single traffic light). This is calculating by 1) keeping track of road users entering the lane (input detector triggers) and ones exiting the lane (output detector triggers), and 2) collecting the vehicle lists from the object list sensors (e.g. radars).

In practice, we keep track of the count of road users in the lane by adding one every time a vehicle passes an input detector and subtracting one when a vehicle passes an output detector. This works in a very similar manner to SUMO simulation engine's detector type "e3" (thus the name). Unlike in the simulation, this approach can cause cumulative error if detectors miss outgoing road users for one reason or another. Because of this, we also reset the counter if the following conditions are met: 1) red starts, and 2) the controller thinks there are no vehicles on this lane. This approach gives us a reasonable estimate for the _number of vehicles_ inside the lane.

In addition to detectors, we might be getting object list type of information (i.e., a list of objects detected to be in this lane by an AI camera, radar, or lidar). This data is augmented with the detector counts (deemed normally to be more reliable) in the following manner: 1) if there are more detected objects in the object list than in the detector count, send the object list and use that as an estimate, 2) do the same if the count is exactly the same, 3) if there are more counted vehicles, expand the list by adding new objects with default values.

Detailed configuration withe examples is given [here](#lanes)

#### Configuring the outputs
After the lanes are defined and configured correctly, output configuration is straightforward: we define a list of lanes (output is an aggregate of object lists in each lane), connection type and channel, as well as frequency. Detailed configuration is given in the [View outputs](#view-outputs-e3) section.


## Configuration file
### Config file and sections
The purpose of the config file is to 1) define connectivity for the service (at the time of writing, only NATS is available), 2) define output data we expect from the service, and 3) define inputs needed for the calculation of outputs and how they are connected.


The configuration file is divided into the following sections:

* **Connectivity** - Settings for accessing data sources (currently only NATS)
* **input_streams** - Data stream configurations (signals, detectors, radar)
* **detlogics** - Detection logic definitions, not operational yet
* **inputs** - Input definitions (detectors, radar lanes, signal groups)
* **lanes** - Traffic lane configurations
* **outputs** - Output configurations for data publishing

Each of these sections are explained below.

### Connectivity

This section defines the data (stream) connections. In the current setting, we only support NATS connections.

The block is defined as follows:
```json
{
"connectivity":{
	"notes": "This is for accessing the data",
	"nats": {
		"server": "HOSTNAME",
		"port": HOSTPORT
        }
    }
},
```

The section can accept following parameters:

| Variable | Explanation | Example Value |
|----------|-------------|----------------|
| HOSTNAME | The hostname or IP address of the NATS server | "localhost" |
| HOSTPORT | The port number for the NATS server connection | 4222 |


Typical use case is to use nats-server running in the localhost and relaying all the messaging via that.

### Input streams
#### The input stream section
This section defines the input streams to be used in traffic indicator calculation. There are currently three input stream types available: 1) `groups` for signal statuses, 2) `detectors` for detector inputs, and 3) `radar` for object lists. In the following subsections we cover each of them.

#### Signal group input stream (`groups`)

Signal group stream is defined with following type of configuration:

```json
    "STREAM_NAME": {
        "connection": "CONNECTION_TYPE",
        "type": "groups",
        "subtype": "SUBTYPE",
        "nats_subject": "SUBSCRIPTION CHANNEL",
        "notes": "DESCRIPTION"
    }

```

Parameters in the sample above takes parameters as follows:

| Variable | Explanation | Example Value |
|----------|-------------|----------------|
| STREAM_NAME | Identifier for the input stream | "sig_inputs" |
| connection | Type of connection protocol | "nats" |
| type | Stream type: `groups` | "groups" |
| subtype | Data source type (e.g., sumo) | "sumo" |
| nats_subject | NATS subject pattern to subscribe to | "group.status.270.*" |
| notes | Description of the stream | "All groups from sumo" |

One should note that typically this stream type subscribes to several different signal group streams (indicated by the `*` in the `nats_subject` example above). The `connection` parameter refers to the `connectivity` section defined in the same configuration file (this is mandatory).

Currently, the subtype has no effect on the operation.

#### Detector input stream (`detectors`)
Detector stream is defined with the following type of configuration:

```json
    "STREAM_NAME": {
        "connection": "CONNECTION_TYPE",
        "type": "groups",
        "subtype": "SUBTYPE",
        "nats_subject": "SUBSCRIPITON CHANNEL",
        "notes": "DESCRIPTION"
    }

```
Parameters in the sample above are as follows:

| Variable | Explanation | Example Value |
|----------|-------------|----------------|
| STREAM_NAME | Identifier for the input stream | "det_inputs" |
| connection | Type of connection protocol | "nats" |
| type | Stream type: `detectors` | "detectors" |
| subtype | Data source type (e.g., sumo) | "sumo" |
| nats_subject | NATS subject pattern to subscribe to |  "detector.status.*" |
| notes | Description of the stream | "All dets from sumo" |

One should note that typically this stream type subscribes to several different detectors streams (indicated by the `*` at the `nats_subject` example above. The `connection`parameter refers to the `connectivity` section defined in the same configuration file (this is mandatory) 

Currently, the subtype has no effect on the operation.


#### Radar input stream (`radar`)

Radar stream is defined with following type of configuration:

```json
    "STREAM_NAME": {
        "connection": "CONNECTION_TYPE",
        "type": "radar",
        "subtype": "SUBTYPE",
        "nats_subject": "SUBSCRIPTION CHANNEL",
        "notes": "DESCRIPTION"
    }

```

Parameters in the sample above takes parameters as follows:

| Variable | Explanation | Example Value |
|----------|-------------|----------------|
| STREAM_NAME | Identifier for the input stream | "radar270.1" |
| connection | Type of connection protocol | "nats" |
| type | Stream type: `radar` | "radar" |
| subtype | Data source type (e.g., sumo) | "sumo" |
| nats_subject | NATS subject for object list subscription | "radar.270.1.objects_port.json" |
| notes | Description of the stream | "Radar pointing north" |

The `connection` parameter refers to the `connectivity` section defined in the same configuration file (this is mandatory).

Currently, the subtype has no effect on the operation.


### Detlogics

This part is to be implemented later. The goal is to define typical detector logic output to be used as part of an Open Controller implementation.


### Inputs
#### Inputs and streams

This section defines inputs for the traffic indicator calculation. This section can be thought of as a "filter" for the input streams, as it defines how to pick parts of the data from the streams defined above and how to assign names to them. Three types of inputs are available: `dets`, `groups`, and `object_filters`, each with their own subsection under `inputs`.

#### Signal groups (`groups`)
Signal groups define which signal group status streams are filtered for use in traffic indicator calculations. Each signal group input is mapped to a specific group identifier from the input stream.

Signal group input is defined with the following configuration:

```json
    "GROUP_ID": {
        "type": "simple",
        "stream": "STREAM_NAME",
        "group": "GROUP_NUMBER"
    }
```

Parameters in the sample above are as follows:

| Variable | Explanation | Example Value |
|----------|-------------|----------------|
| GROUP_ID | Identifier for the signal group input | "group1" |
| type | Input type: `simple` | "simple" |
| stream | Reference to input stream defined in `input_streams` | "sig_inputs" |
| group | Signal group number to filter from the stream | "1" |

The `stream` parameter refers to a stream defined in the `input_streams` section (typically a `groups` type stream). Multiple signal group inputs can reference the same stream but filter different group numbers. These inputs are then used in lane definitions and output configurations to associate traffic indicators with specific signal groups.

#### Detectors (`dets`)

Detector inputs define which detector status streams are filtered for use in traffic indicator calculations. Each detector input is mapped to a specific detector identifier from the input stream and can be configured to trigger on state changes.

Detector input is defined with the following configuration:

```json
    "DETECTOR_ID": {
        "type": "TRIGGER_TYPE",
        "stream": "STREAM_NAME",
        "name": "DETECTOR_NAME",
        "vtype": "VEHICLE_TYPE"
    }
```

Parameters in the sample above are as follows:

| Variable | Explanation | Example Value |
|----------|-------------|----------------|
| DETECTOR_ID | Identifier for the detector input | "2-002" |
| type | Trigger type: `rising_edge`, `falling_edge`, or `change` | "falling_edge" |
| stream | Reference to input stream defined in `input_streams` | "det_inputs" |
| name | Detector name/identifier from the stream | "2-002" |
| vtype | Vehicle type for filtering (optional) | "tram_type" |

The `stream` parameter specifies the input stream that the detector will monitor, as defined in the `input_streams` section of the configuration. 

The `type` parameter determines the conditions under which the detector will trigger a state change. There are three options available for this parameter:
1. **Rising Edge** (`rising_edge`): The detector triggers when the input signal transitions from a low state to a high state.
2. **Falling Edge** (`falling_edge`): The detector triggers when the input signal transitions from a high state to a low state.
3. **Change** (`change`): The detector triggers on both rising and falling edges, allowing it to respond to changes in either direction.

#### Object filters (`object_filters`)

Object filters define how object lists (coming from radars for example) are processed for use in traffic indicator calculations. Each object filter maps to a specific radar stream and lane configuration.

Object filter input is defined with the following configuration:

```json
    "FILTER_ID": {
        "type": "simple",
        "stream": "STREAM_NAME",
        "lane": "LANE_NUMBER"
    }
```

Parameters in the sample above are as follows:

| Variable | Explanation | Example Value |
|----------|-------------|----------------|
| FILTER_ID | Identifier for the object filter | "270_1_0" |
| type | Filter type: `simple` | "simple" |
| stream | Reference to input stream defined in `input_streams` | "radar270.1" |
| lane | Lane number to filter from the radar stream | "0" |

The `stream` parameter refers to a stream defined in the `input_streams` section (typically a `radar` type stream). Multiple object filters can reference the same stream but filter different lane numbers. These filters are then referenced in lane definitions to associate object detection with specific traffic lanes.

### Lanes

Lanes section defines lanes to be used for calculating different views. In essence, we use input and output detectors as well as object list data (e.g. from radar) to provide a reasonable estimate for the amount of road users in a given lane. 

The lane is configured as follows:
```json
    "LANE_ID": {
        "name": "LANE_NAME",
        "in_dets": ["INPUT_DETECTOR_IDS"],
        "out_dets": ["OUTPUT_DETECTOR_IDS"],
        "object_lists": ["OBJECT_FILTER_IDS"],
        "lane_main_type": "VEHICLE_TYPE",
        "notes": "DESCRIPTION"
    }
```

Parameters in the sample above are as follows:

| Variable | Explanation | Example Value |
|----------|-------------|----------------|
| LANE_ID | Identifier for the lane | "grp1_1" |
| name | Descriptive name for the lane | "Group 1 lane 1" |
| in_dets | Array of input detector IDs from `inputs.dets` | ["1-040"] |
| out_dets | Array of output detector IDs from `inputs.dets` | ["1-002"] |
| object_lists | Array of object filter IDs from `inputs.object_filters` | ["270_2_0"] |
| lane_main_type | Vehicle type for the lane (optional) | "tram_type" |
| notes | Description of the lane | "Approach from west" |

The `in_dets` parameter defines detectors that trigger when vehicles enter the lane section, while `out_dets` defines detectors that trigger when vehicles exit. The `object_lists` parameter references object filters that provide radar-based tracking within the lane. The optional `lane_main_type` parameter is used to specify lanes dedicated to specific vehicle types, such as tram lanes (this is only used for the outputs, not for filtering).

### Outputs

#### View outputs (`e3`)
Currently, this is the output type we use. In essence, this output emits (at a given frequency) our current best estimate of vehicles in the lanes mapped in this view.

Views output is defined with the following configuration:

```json
    "VIEW_ID": {
        "connection": "CONNECTION_TYPE",
        "type": "e3",
        "nats_output_subject": "OUTPUT_SUBJECT",
        "trigger": "TRIGGER_TYPE",
        "trigger_time": FREQUENCY,
        "lanes": ["LANE_IDS"],
        "group": "GROUP_ID",
        "detectors_broken": BOOLEAN,
        "notes": "DESCRIPTION"
    }
```

Parameters in the sample above are as follows:

| Variable | Explanation | Example Value |
|----------|-------------|----------------|
| VIEW_ID | Identifier for the view output | "group1_view" |
| connection | Type of connection protocol | "nats" |
| type | Output type: `e3` | "e3" |
| nats_output_subject | NATS subject for publishing the view | "group.e3.270.1" |
| trigger | Trigger type: `time` is the only option for now | "time" |
| trigger_time | Emission frequency in seconds (for time trigger) | 1.0 |
| lanes | Array of lane IDs from `lanes` section | ["grp1_1", "grp1_2"] |
| group | Associated signal group ID from `inputs.groups` | "group1" |
| detectors_broken | Boolean flag indicating detector malfunction (optional) | false |
| notes | Description of the view | "Approach from north" |

The `lanes` parameter aggregates multiple lanes into a single view, allowing the output to represent the combined vehicle count across several traffic lanes. The `group` parameter associates the view with a specific signal group for coordination purposes. When `detectors_broken` is set to `true`, the system will rely on alternative data sources (such as radar object lists) for vehicle estimation.

## Example file

Below is a simplified configuration with full sections. For an operational configuration, see examples under `/models`, for example `models/testmodel/indicators.md`

```json
{
"connectivity":{
	"notes": "This is for accessing the data",
	"nats": {
		"server": "localhost",
		"port": 4222
    }
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
        },
    "radar270.2": {
        "connection": "nats",        
        "type": "radar",
        "subtype": "sumo",
        "nats_subject": "radar.270.2.objects_port.json",
        "notes": "Will subscribe to radar pointing west"
        },
    "radar270.3": {
        "connection": "nats",
        "type": "radar",
        "subtype": "sumo",
        "nats_subject": "radar.270.3.objects_port.json",
        "notes": "Will subscribe to radar pointing south"
        }
    },

"detlogics":{
    "tram9_request_detlogic":{
        "type": "two_det_switch",
        "notes": "One detector swithces the request on, another off",
        "detectors": {
            "request": "R8PY",
            "clear": "R8KU"
        },
        "request_trigger": "rising_edge",
        "clear_trigger": "falling_edge"
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
        },
        "5-002": {
            "type": "falling_edge",
            "stream": "det_inputs",
            "name": "5-002"
        },
        "5-040": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "5-040"
        },
        "1-002": {
            "type": "falling_edge",
            "stream": "det_inputs",
            "name": "1-002"
        },
        "1-040": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "1-040"
        },
        "6-002A": {
            "type": "falling_edge",
            "stream": "det_inputs",
            "name": "6-002A"
        },
        "6-040": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "6-040"
        },
        "6-002B": {
            "type": "falling_edge",
            "stream": "det_inputs",
            "name": "6-002B"
        },
        "6-030": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "6-030"
        },
        "7-020": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "7-020"
        },
        "7-001": {
            "type": "falling_edge",
            "stream": "det_inputs",
            "name": "7-001"
        },
        "R8PY": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "R8PY",
            "vtype": "tram_type"
        },
        "R8KU": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "R8KU",
            "vtype": "tram_type"
        },
        "R9PY": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "R9PY",
            "vtype": "tram_type"
        },
        "R9KU": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "R9KU",
            "vtype": "tram_type"
        },
        "R3PY": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "R3PY",
            "vtype": "tram_type"
        },
        "R3KU": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "R3KU",
            "vtype": "tram_type"
        },
        "R4PY": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "R4PY",
            "vtype": "tram_type"
        },
        "R4KU": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "R4KU",
            "vtype": "tram_type"
        },
        "test_request": {
            "type": "rising_edge",
            "stream": "det_inputs",
            "name": "3-002R",
            "vtype": "tram_type"
        },
        "test_clear": {
            "type": "falling_edge",
            "stream": "det_inputs",
            "name": "3-002R",
            "vtype": "tram_type"
        }

    },
    "object_filters":{
        "270_1_0": {
            "type": "simple",
            "stream": "radar270.1",
            "lane": "0"
        },
        "270_1_1": {
            "type": "simple",
            "stream": "radar270.1",
            "lane": "1"
        },
        "270_2_0": {
            "type": "simple",
            "stream": "radar270.2",
            "lane": "3"
        },
        "270_3_1": {
            "type": "simple",
            "stream": "radar270.3",
            "lane": "1"
        },
        "270_3_2": {
            "type": "simple",
            "stream": "radar270.3",
            "lane": "0"
        },
        "270_3_3": {
            "type": "simple",
            "stream": "radar270.3",
            "lane": "5"
        }
    },
    "groups": {
        "group1": {
            "type": "simple",
            "stream": "sig_inputs",
            "group": "1"
        },
        "group2": {
            "type": "simple",
            "stream": "sig_inputs",
            "group": "2"
        },
        "group3": {
            "type": "simple",
            "stream": "sig_inputs",
            "group": "3"
        },
        "group4": {
            "type": "simple",
            "stream": "sig_inputs",
            "group": "4"
        },
        "group5": {
            "type": "simple",
            "stream": "sig_inputs",
            "group": "5"
        },
        "group6": {
            "type": "simple",
            "stream": "sig_inputs",
            "group": "6"
        },
        "group7": {
            "type": "simple",
            "stream": "sig_inputs",
            "group": "7"
        },
        "group8": {
            "type": "simple",
            "stream": "sig_inputs",
            "group": "8"
        },
        "group9": {
            "type": "simple",
            "stream": "sig_inputs",
            "group": "9"
        }
    }
},

"lanes":{
    "grp1_1":{
        "name": "Group 1 lane 1",
        "in_dets": ["1-040"],
        "out_dets": ["1-002"],
        "object_lists":["270_2_0"],
        "notes": "Approach from west"
    },
    "grp2_1":{
        "name": "Group 2 lane 1",
        "in_dets": ["2-040"],
        "out_dets": ["2-002"],
        "object_lists":["270_1_0"],
        "notes": "Approach from north"
    },
    "grp3_1":{
        "name": "Group 3 lane 1",
        "in_dets": ["R3PY"],
        "out_dets": ["R3KU"],
        "object_lists":[],
        "lane_main_type": "tram_type",
        "notes": "Tram lane from west"
    },
    "grp4_1":{
        "name": "Group 4 lane 1",
        "in_dets": ["R4PY"],
        "out_dets": ["R4KU"],
        "object_lists":[],
        "lane_main_type": "tram_type",
        "notes": "Tram line from north"
    },
    "grp5_1":{
        "name": "Group 5 lane 1",
        "in_dets": ["5-040"],
        "out_dets": ["5-002"],
        "object_lists":["270_1_1"],
        "notes": "Approach from north"
    },
    "grp6_1":{
        "name": "Group 6 lane 1",
        "in_dets": ["6-040"],
        "out_dets": ["6-002A"],
        "object_lists":["270_3_1"],
        "notes": "Approach from north"
    },
    "grp6_2":{
        "name": "Group 6 lane 2",
        "in_dets": ["6-030"],
        "out_dets": ["6-002B"],
        "object_lists":["270_3_2"],
        "notes": "Approach from north"
    },
    "grp7_1":{
        "name": "Group 7 lane 1",
        "in_dets": ["7-020"],
        "out_dets": ["7-001"],
        "object_lists":["270_3_3"],
        "notes": "Approach from north"
    },
    "grp8_1":{
        "name": "Tram lane for Group 8",
        "in_dets": ["R8PY"],
        "out_dets": ["R8KU"],
        "object_lists":[],
        "lane_main_type": "tram_type",
        "notes": "Special lane for tram"
    },
    "grp9_1":{
        "name": "Tram lane for Group 9",
        "in_dets": ["R9PY"],
        "out_dets": ["R9KU"],
        "object_lists":[],
        "lane_main_type": "tram_type",
        "notes": "Special lane for tram"
    },
    "tramtest": {
        "name": "Tram test lane",
        "in_dets": ["test_request"],
        "out_dets": ["test_clear"],
        "object_lists":[],
        "lane_main_type": "tram_type",
        "notes": "Special lane for tram, test"
    }
},

"outputs":{
    "tram9_request":{
        "connection": "nats",
        "type": "detlogic",
        "nats_output_subject": "group.request.270.9",
        "trigger": "change",
        "function": "tram9_request_detlogic",
        "notes": "Will output the request for tram for group 9"
        },
    "group1_view":{
        "connection": "nats",
        "type": "e3",
        "nats_output_subject": "group.e3.270.1",
        "trigger": "time",
        "trigger_time": 1.0,
        "lanes": ["grp1_1"],
        "group": "group1",
        "notes": "Will send queue request"
        },    
    "group2_view":{
        "connection": "nats",
        "type": "e3",
        "nats_output_subject": "group.e3.270.2",
        "trigger": "time",
        "trigger_time": 1.0,
        "lanes": ["grp2_1"],
        "group": "group2",
        "detectors_broken": true, 
        "notes": "Detectors broken"
        },
    "group3_view":{
        "connection": "nats",
        "type": "e3",
        "nats_output_subject": "group.e3.270.3",
        "trigger": "time",
        "trigger_time": 1.0,
        "lanes": ["grp3_1"],
        "group": "group3",
        "notes": "Tram line from north using group 3"
        },
    "group4_view":{
        "connection": "nats",
        "type": "e3",
        "nats_output_subject": "group.e3.270.4",
        "trigger": "time",
        "trigger_time": 1.0,
        "lanes": ["grp4_1"],
        "group": "group4",
        "notes": "Tram line from north using group 4"
        },
    "group5_view":{
        "connection": "nats",
        "type": "e3",
        "nats_output_subject": "group.e3.270.5",
        "trigger": "time",
        "trigger_time": 1.0,
        "lanes": ["grp5_1"],
        "group": "group5",
        "detectors_broken": true,
        "notes": "Will send queue request"
        },
    "group6_view":{
        "connection": "nats",
        "type": "e3",
        "nats_output_subject": "group.e3.270.6",
        "trigger": "time",
        "trigger_time": 1.0,
        "lanes": ["grp6_1", "grp6_2"],
        "group": "group6",
        "notes": "From port to the north"
        },
    "group7_view":{
        "connection": "nats",
        "type": "e3",
        "nats_output_subject": "group.e3.270.7",
        "trigger": "time",
        "trigger_time": 1.0,
        "lanes": ["grp7_1"],
        "group": "group7",
        "notes": "From port to the north"
        },
    "group8_view":{
        "connection": "nats",
        "type": "e3",
        "nats_output_subject": "group.e3.270.8",
        "trigger": "time",
        "trigger_time": 1.0,
        "lanes": ["grp8_1"],
        "group": "group8",
        "notes": "Tram line from north using group 8"
        },
    "group9_view":{
        "connection": "nats",
        "type": "e3",
        "nats_output_subject": "group.e3.270.9",
        "trigger": "time",
        "trigger_time": 1.0,
        "lanes": ["grp9_1"],
        "group": "group9",
        "notes": "Tram line from north using group 9"
        },
    "tramtest_view":{
        "connection": "nats",
        "type": "e3",
        "nats_output_subject": "group.e3.270.10",
        "trigger": "time",
        "trigger_time": 1.0,
        "lanes": ["tramtest"],
        "group": "group3",
        "notes": "Testing the closeup tram"
        }
    }
}
```