# Simengine configuration

The simulation engine uses a json-configuration file. 
In section "simulation" the Sumo-configuration file is defined (sumocfg).
The Sumo-model can involve one or more intersections. 
All the sensors and detectors should have unique names.
Currently one "mode" is supported namely "nats". 
All the messages go through the nats message broker.
For the nats-server you have define an IP-address and port number. 

Therest of the file is divided into the following sections.
In the section "outputs" all outputs are defined including
detectors, signals and radars. The signal control inputs are
defined the section "inputs" The radars are specified in the 
"radars" section, but the radars actually used are listed
in the "rad_outputs" section. 

The detector and signal outputs have the value for "trigger".
If the value is "change" then new message is sent only when the status has changed.
The value "update" means the that new message is sent per each update of the simengine.
The "update" mode can generate a lot of redundant messages, but with radars only the "update" mode is used.

There is also a mapping mode for the detector and signal data. 
The mode "direct" means that the Sumo-name is used directly in the output message. 
Otherwise a mapping is needed, which is a lookup table converting the Sumo-name to something else.

The NATS-channel name (or topic) consists of prefix and the name of the detector or signal group.
Each message-type has its own "topic_prefix", which indicates how the message is processed in the receiving end.
For example "detector.control" prefix is used in the hardware-in-the-loop simulation to control the
detector states of the real signal controller. If only detector status is needed, then the prefix would be "detector.status".

```json
{
"simulation":{
	"notes": "These are parameters for running the simulation",
	"sumocfg": "../cfgFiles/JS_266-267_HWIL.sumocfg",
	"mode": "nats",
	"nats": {
		"ip": "10.8.0.36",
		"port": 4222
	}
},

"outputs":{
    "det_outputs": {
        "type": "detector",
        "trigger": "change",
        "det_mapping_mode": "direct",
        "topic_prefix": "detector.control",
        "det_map": {
            "sumo_det1":"det1"
        },
        "notes": "Ths is the detector output"
    },

    "sig_outputs": {
        "type": "group",
        "trigger": "change",
        "controller_mapping_mode": "direct",
        "topic_prefix": "group.status",
        "controller_map": {
            "1": "266"
        },
        "signal_mapping_mode": "direct",
        "signal_map": {
            "1": "1"
        }
    },

"rad_outputs":{
        "type": "radar",
        "trigger": "update",
        "radars": ["int_266_1", "int_266_3", "int_267_3", "int_267_1", "int_267_2"]
    }
},
```
The input side of the simengine is configured in the "inputs" section. 
Traffic signal inputs from the controller are configured within the section "sig_inputs".
The key values are same than with the outputs. 
In most cases the mapping modes are of type "direct" meaning that there is
no mapping between names in Sumo and the Open Controller. 


```json
"inputs":{
    "sig_inputs": {
        "type": "group",
        "trigger": "update",
        "topic_prefix": "group.control",
        "controller_mapping_mode": "direct",
        "controller_map": {
            "266": "1"
        },
        "signal_mapping_mode": "direct",
        "signal_map": {
            "1": "1"
        }
    }
},
```
Each radar is defined in its own section starting with key value thast is the name of the radar.
Any number of radars can be predefined, but only the ones lited in the "rad_outputs" sections will be used.
Here the topic has fixed prefix "radar", but the full topic name has to be given under the "topic". 
The topic name consists of "radar" + "intersection number" + "radar number" + "object_port.json".
The "area_of_interest" is a polygon of geocoordinates. The polygon can have any number of points. 
Only vehicles inside the polygon will be counted in and sent out through the NATS-channel. 
In Sumo the lanes are defined bya string consisting of edge-name + "-" + lane number. 
The lane mapping is needed especially if the controller is intended for live control in the field.
In that case, the Sumo-lane are mapped to radar-lanes of the real radars in the field. 
This way the simulated controller will work directly in the field. 

```json
"radars":{
    "int_266_1":{
        "sink_id": 1,
        "service": "nats_server",
        "topic": "radar.266.1.objects_port.json",
        "data_type": "geo",
        "source": "sumo_radar",
        "trigger": "update",
        "area_of_interest": [
            [60.16483826969739, 24.920751907321858],
            [60.16652792073333, 24.92068669833371],
            [60.16650505434616, 24.921310500131423],
            [60.16488476697155, 24.92154032184637]
            ],
        "description": "266 North",
        "lane_map":{
            "-Mech06_0": 5,
            "-Mech07_0": 5,
            "-Mech06_1": 2,
            "-Mech07_1": 2,
            "-Mech06_2": 1,
            "-Mech07_2": 1,
            "-Mech06_3": 0,
            "-Mech07_3": 0          
            }
        }
    }
}
```
