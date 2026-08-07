import numpy as np
from stable_baselines3 import DQN, PPO
from stable_baselines3.common.base_class import BaseAlgorithm

from services.control_engine.src.detectors.area_detector import (
    TransitAreaDetector,
)
from services.control_engine.src.geometry.movements import LanePressureConfig


def get_observation(
    current_phase_idx: int,
    seconds_in_current_phase: float,
    phase_count: int,
    pressure_configs: list[LanePressureConfig],
    transit_detections: np.ndarray,
) -> np.ndarray:
    """Get observation in Bumblebee standard format.

    Args:
        current_phase_idx: The index of the controllers current phase.
        seconds_in_current_phase: How long the agent has remained in the current state.
        phase_count: Number of phases in the controller.
        pressure_configs: Configurations for calculating lane wise pressures.
        transit_detections: Vehicle counts from transit detectors.

    Returns:
        Lane wise pressures, one-hot encoded phase in an array,
        the time agent has remained in the current state, and transit detections.

    """
    num_pressures = len(pressure_configs)
    obs = np.zeros(
        num_pressures + phase_count + 1 + transit_detections.shape[0],
        dtype=np.float32,
    )

    for i, pressure_config in enumerate(pressure_configs):
        obs[i] = _get_lane_pressure(pressure_config)

    # Add one-hot-encoded phase.
    obs[num_pressures + current_phase_idx] = 1.0

    # Add current phase duration.
    obs[num_pressures + phase_count] = seconds_in_current_phase

    # Add transit detections to the end of the array.
    obs[num_pressures + phase_count + 1 :] = transit_detections

    return obs


def _get_lane_pressure(pressure_config: LanePressureConfig) -> float:
    q_in = pressure_config.incoming_detector.vehicle_count

    weighted_q_out = sum(
        m.theta * m.detector.vehicle_count for m in pressure_config.movements
    )

    total_theta = sum(m.theta for m in pressure_config.movements)

    return (total_theta * q_in) - weighted_q_out


def get_presslight_reward(
    pressure_configs: list[LanePressureConfig],
    transit_detectors: list[TransitAreaDetector],
) -> float:
    """Calculate reward based on lane pressures and transit vehicle queues."""
    pressure_penalty = 0.0
    for pressure_config in pressure_configs:
        pressure = _get_lane_pressure(pressure_config)
        pressure_penalty += abs(pressure)

    transit_penalty = 0.0
    for det in transit_detectors:
        transit_penalty += det.vehicle_count * 5

    return -pressure_penalty - transit_penalty


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
