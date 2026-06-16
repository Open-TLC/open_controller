class TrafficEnv:
    """TrafficEnv is used to train and run RL models in Open Controller Bumblebee.
    TrafficEnv uses SimEngine and SUMO to simulate traffic on a network. It can
    provide observations based on detector readings from the simulation, execute
    signal group states, and calculate statistics about the traffic situation. The
    environment is also responsible for ensuring the safety of traffic by blocking
    conflicting signal phases.
    """

    def __init__(self) -> None:
        pass
