# Bumblebee

## TrafficEnv

Bumblebee's TrafficEnv is a Gymnasium environment used to train and evaluate RL models on traffic signal control. The environment can provide observations and statistics about the traffic situation and execute signal states on configured signal groups.

### Observation

The environment can be configured to return various observations from the simulation, depending on the sensors in use and the specific data you want to utilize. Possible categories include (as sensor-specific averages):

- Number of vehicles
- Vehicle speed
- Vehicle delay (time loss)
- Number of vehicle stops
- Number of heavy traffic vehicles
- Number of public transit vehicles
- Number of rail traffic vehicles
- Loop occupancy rate
- Loop vehicle length
- Signal state (one-hot encoded)
- Duration of the current signal state

The desired observations are returned as a list of numerical values. The model must support a continuous observation space, though in practice, nearly all commonly used algorithms support this.

### Reward

A reward function is passed to the environment during initialization. This function has access to all the observations specified in the configuration. A set of pre-built reward functions must be available out of the box.

### Action

When the environment is initialized, it automatically generates a list of all possible allowed signal phases. Each phase is assigned its own integer index. The agent's task is to return the index of its desired phase, after which the environment will attempt to transition the simulation to that target state. The environment is responsible for translating this phase into signal states that SUMO can understand, as well as handling the assignment of intermediate yellow and red-yellow transition phases. The length of each step—meaning how frequently the states are updated—is also configured during the environment's initialization.

The action space for this type of environment is discrete. The number of available actions is exactly equal to the number of possible phases.

## SimEngine

SimEngine is a simulation runner that is designed to work in RL applications. It can run simulations in steps to allow for neural network training which requires fine grained control over environment. SimEngine is designed to be used through Bumblebee's TrafficEnv environment. SimEngine can run in both headless and GUI mode to allow for quick training and visual debugging with the same environment.

## Trainer

Script used for training models.

## Evaluator

Script used for evaluating models.

## Controller

Signal controller that uses a trained model to decide signal timings.
