# Bumblebee

## TrafficEnv

Bumblebee's TrafficEnv is a Gymnasium environment used to train and evaluate RL models on traffic signal control. The environment provides observations about the traffic situation and execute signal states on configured signal groups.

## SimEngine

SimEngine is a simulation runner that is designed to work in RL applications. It can run simulations in steps to allow for neural network training which requires fine grained control over environment. SimEngine is designed to be used through Bumblebee's TrafficEnv environment.

## Trainer

Trainer, as the name suggests, is a training script for Bumblebee models. It will train a model with specified algorithm and for specified number of steps with a specified SUMO configuration.

To run trainer, you need to have:

1. `uv` [installed](https://docs.astral.sh/uv/getting-started/installation/) and added to path.
2. SUMO configuration with at least one signallized intersection. Make sure to include E2 or E3 detectors for **ALL** approaching lanes.
3. Bumblebee configuration file in the following format.

```json
{
	"algorithm": "ppo",  // This can be either PPO, DQN or A2C
	"training_steps": 100000,  // Should be above 10^5 for simple situation and higher for more complex intersections or traffic flows
	"simengine": {
		"sumo_file": "path/to/simulation.sumocfg",
		"step_length": 1  // Single simulation step simulates 1 second of traffic
	},
	"traffic_env": {
		"episode_steps": 3600,  // One episode simulates 3600 agent steps
		"sumo_name": "controller1",  // SUMO ID of the traffic controller
		"step_length": 1,  // One agent step advances the simulation by 1 step

		// Regular intergreen matrix (N x N, where N = number of logical signal groups)
		"intergreens": [
			[0, 0, 0, 3, 0, 0],
			[0, 0, 0, 3, 3, 3],
			[0, 0, 0, 0, 0, 3],
			[3, 3, 0, 0, 0, 3],
			[0, 3, 0, 0, 0, 0],
			[0, 3, 3, 3, 0, 0]
		],

		// Mapping of physical SUMO signal links to logical signal groups.
		// - Index of this list: The specific signal link ID in the SUMO network.
		// - Value at index: The corresponding logical group index (from the intergreen matrix).
		"group_outputs": [0, 1, 2, 3, 4, 5],

        // Detector configurations in the AreaDetector configuration format
		"detectors": [
			{
				"type": "e2_detector",  // Can be either e2_detector or e3_detector
				"id": "e2_0"  // SUMO ID of the detector
			},
			{
				"type": "e2_detector",
				"id": "e2_1"
			},
			{
				"type": "e2_detector",
				"id": "e2_2"
			},
			{
				"type": "e2_detector",
				"id": "e2_3"
			},
			{
				"type": "e2_detector",
				"id": "e2_4"
			},
			{
				"type": "e2_detector",
				"id": "e2_5"
			}
		]
	}
}
```

To install project dependencies run the following command in Open Controller project root.

```bash
uv sync
```

To train the model, run the following command in Open Controller project root.

```bash
uv run -m services.control_engine.src.bumblebee.trainer --conf-file path/to/bumblebee/conf.json --model-file path/to/result/file.zip --tensorboard path/to/training/log/dir/
```

## Controller

Signal controller that uses a trained model to decide signal timings.

#opencontroller
