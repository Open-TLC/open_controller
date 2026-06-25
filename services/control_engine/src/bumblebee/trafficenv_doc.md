# Traffic Environment – Bumblebee TrafficEnv

## Observation

By default, Bumblebee uses an observation vector recommended in literature, consisting of the detected vehicle counts and the current state of the controller. Vehicle counts specifically have been observed to yield the shortest travel times, which can be considered an indicator of its performance effectiveness.

The desired observations are returned as a list of numbers. The model used must support a continuous observation space, though in practice, virtually all algorithms used support this.

By connecting the environment to NATS, the states of adjacent intersections can be queried in multi-controller scenarios. This allows multi-agent (multi-controller) systems to remain aware of each other's actions and learn to cooperate.

## Reward

By default, Bumblebee uses the number of detected vehicles for its reward function, as recommended in literature. The reward also accounts for the number of vehicles that have waited excessively long—meaning they have teleported in SUMO. Formally, the reward function is defined as follows:

$
R=-\sum_{i=1}^{n_s} n_v^i - 1000\cdot n_t,\text{ where } n_s=\text{Number of sensors},\ n_v^i=\text{Number of vehicles at sensor } i\text{ and } n_t=\text{Number of teleported vehicles}
$

## Action

When the environment is initialized, it automatically creates a list of all possible valid phases. Each phase has its own unique index. The agent's task is to return the index of its desired phase, after which the environment attempts to transition the simulation into that desired state.

The environment is responsible for translating this phase into signal states understood by SUMO and managing the assignment of yellow and red-yellow intervals. The length of each step (i.e., how frequently states are updated) is also configured during environment initialization.

The action space for this type of environment is discrete. The number of available actions is equal to the number of possible phases.

