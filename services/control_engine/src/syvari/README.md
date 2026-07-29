# SYVARI

Implementation of SYVARI control logic for Open Controller. SYVARI is a signal control strategy designed to allow for transit priorities in coordinated signals. It is widely used in Finland and thus implementing it in Open Controller is important.

Learn more about SYVARI [here](https://salonen.info/syvari/).

## Configuring

SYVARI controller can be configured with a JSON file similar to other Open Controller configurations. Here is an example configuration file:

```json
{
    "timer": {
        "timer_type": "cycle",  // Cycle timer is needed for SYVARI
        "time_step": 0.1,
        "real_time_multiplier": 1,
        "cycle_length": 60  // Length of a single cycle
    },

    "sumo": {
        "graph": true,  // Graphical mode using SUMO GUI or not
        "file_name": "path/to/simulation.sumocfg"
    },

    "active_controllers": [
        "controller_1"
    ],

    "controllers": {
        "controller_1": {
            "sumo_name": "controller_1",
            "print_status": false,
            "type": "syvari",

            // Logical signal groups are mapped to SUMO links
            "group_outputs": [
                "east_fr", "east_fr",
                "east_l",
                "east_fr",

                "south_frl", "south_frl", "south_frl",

                "west_fr", "west_fr",
                "west_l",
                "west_fr",

                "north_frl", "north_frl", "north_frl"
            ],

            "signal_groups": {
                "east_fr": {
                    "sync_start": 0,  // Preferred green start time in cycle
                    "sync_end": 25,  // Preferred green end time in cycle
                    "min_green": 3,  // Minimum green time
                    "min_guaranteed": 5,  // Minimum green time that the group can always extend to
                    "priority_max": 45,  // Maximum priority extended time of group
                    "detectors": ["e3_e_1", "e3_e_3"] // Forward + right turning lane and tram
                },
                "west_fr": {
                    "sync_start": 0,
                    "sync_end": 25,
                    "min_green": 3,
                    "min_guaranteed": 5,
                    "priority_max": 45,
                    "detectors": ["e3_w_1", "e3_w_3"]
                },

                "east_l": {
                    "sync_start": 25,
                    "sync_end": 35,
                    "min_green": 3,
                    "min_guaranteed": 5,
                    "detectors": ["e3_e_2"] // Left turning lane
                },
                "west_l": {
                    "sync_start": 25,
                    "sync_end": 35,
                    "min_green": 3,
                    "min_guaranteed": 5,
                    "detectors": ["e3_w_2"]
                },

                "south_frl": {
                    "sync_start": 35,
                    "sync_end": 55,
                    "min_green": 3,
                    "min_guaranteed": 5,
                    "detectors": ["e3_s_1"]
                },
                "north_frl": {
                    "sync_start": 35,
                    "sync_end": 55,
                    "min_green": 3,
                    "min_guaranteed": 5,
                    "detectors": ["e3_n_1"]
                }
            },

            "detectors": [
                {
                    "type": "e3_detector",
                    "id": "e3_e_1"
                },
                {
                    "type": "e3_detector",
                    "id": "e3_e_2"
                },
                {
                    "type": "e3_detector",
                    "id": "e3_e_3"
                },
                {
                    "type": "e3_detector",
                    "id": "e3_w_1"
                },
                {
                    "type": "e3_detector",
                    "id": "e3_w_2"
                },
                {
                    "type": "e3_detector",
                    "id": "e3_w_3"
                },
                {
                    "type": "e3_detector",
                    "id": "e3_s_1"
                },
                {
                    "type": "e3_detector",
                    "id": "e3_n_1"
                }
            ],
            
            // Order of signal groups in phases and intergreens
            "group_list": [
                "east_fr",
                "west_fr",
                "east_l",
                "west_l",
                "south_frl",
                "north_frl"
            ],

            // 1 means green, 0 means red
            "phases": [
                [1, 1, 0, 0, 0, 0],
                [0, 0, 1, 1, 0, 0],
                [0, 0, 0, 0, 1, 1]
            ],

            // Intergreen yellow + red times in seconds
            "intergreens": [
                [0, 0, 3, 3, 3, 3],
                [0, 0, 3, 3, 3, 3],
                [3, 3, 0, 0, 3, 3],
                [3, 3, 0, 0, 3, 3],
                [3, 3, 3, 3, 0, 0],
                [3, 3, 3, 3, 0, 0]
            ]
        }
    }
}
```

If you want to run multiple coordinated controllers, you just add them under `controllers` and set their synchronized times to line up with the first controller. This way the controllers flexibly switch between coordination and individual extensions.
