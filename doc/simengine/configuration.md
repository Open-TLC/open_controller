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
        "topic_prefix": "group.data",
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



```json
"inputs":{
    "sig_inputs": {
        "type": "group",
        "trigger": "update",
        "topic_prefix": "group.status",
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
