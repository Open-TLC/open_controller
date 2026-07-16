import numpy as np
from stable_baselines3 import DQN, PPO
from stable_baselines3.common.base_class import BaseAlgorithm

from services.control_engine.src.detectors.area_detector import AreaDetector
from services.control_engine.src.geometry.movements import LanePressureConfig


def get_observation(
    current_phase_idx: int,
    phase_count: int,
    pressure_configs: list[LanePressureConfig],
) -> np.ndarray:
    """Get observation in Bumblebee standard format.

    Args:
        current_phase_idx: The index of the controllers current phase.
        phase_count: Number of phases in the controller.
        pressure_configs: Configurations for calculating lane wise pressures.

    Returns:
        Lane wise pressures and one-hot encoded phase in an array.

    """
    num_pressures = len(pressure_configs)
    obs = np.zeros(num_pressures + phase_count, dtype=np.float32)

    for i, pressure_config in enumerate(pressure_configs):
        obs[i] = get_lane_pressure(pressure_config)

    obs[len(pressure_configs) + current_phase_idx] = 1.0

    return obs


def get_lane_pressure(pressure_config: LanePressureConfig) -> float:
    q_in = pressure_config.incoming_detector.vehicle_count

    pressure = 0.0
    for m in pressure_config.movements:
        q_out = m.detector.vehicle_count
        pressure += m.theta * (q_in - q_out)

    return pressure


def get_presslight_reward(pressure_configs: list[LanePressureConfig]) -> float:
    total_penalty = 0.0
    for pressure_config in pressure_configs:
        pressure = get_lane_pressure(pressure_config)
        total_penalty += abs(pressure) ** 1.5

    return -total_penalty


def calculate_pressure(upstream: AreaDetector, downstream: AreaDetector) -> float:
    """Calculate the pressure of a link."""
    return max(0, (upstream.vehicle_count - downstream.vehicle_count))


def load_model(model_type: str, filename: str) -> BaseAlgorithm:
    """Load StableBaselines3 model from a file.

    Args:
        model_type: Model algorithm (currently supported: ppo, dqn).
        filename: Path to the saved model file.

    Returns:
        Model object loaded from the file.

    """
    model: BaseAlgorithm
    if model_type == "ppo":
        model = PPO.load(filename)
    elif model_type == "dqn":
        model = DQN.load(filename)
    else:
        raise ValueError("Unknown model type: ", model_type)

    return model
