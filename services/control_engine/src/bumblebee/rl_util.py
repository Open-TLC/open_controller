import numpy as np
from stable_baselines3 import DQN, PPO
from stable_baselines3.common.base_class import BaseAlgorithm

from services.control_engine.src.geometry.movements import LanePressureConfig


def get_observation(
    current_phase_idx: int,
    seconds_in_current_phase: float,
    phase_count: int,
    pressure_configs: list[LanePressureConfig],
    transit_detections: np.ndarray,
    phase_active_lanes: np.ndarray,
) -> dict[str, np.ndarray]:
    """Get observation formatted directly per phase for FRAP models.

    Args:
        current_phase_idx: Index of the current active phase.
        seconds_in_current_phase: Number of steps agent has remained in current phase.
        phase_count: Total number of candidate phases.
        pressure_configs: Lane pressure configurations for all movements.
        transit_detections: Phase wise transit detections.
        phase_active_lanes: Matrix representing active lanes per phase.

    Returns:
        Dictionary containing actual observation and an action mask.

    """
    num_lanes = len(pressure_configs)

    # Lane wise pressures are calculated.
    lane_pressures = np.zeros(num_lanes, dtype=np.float32)
    for i, config in enumerate(pressure_configs):
        lane_pressures[i] = _get_lane_pressure(config)

    # Phase pressure is calculated from lane wise pressures.
    phase_pressures = phase_active_lanes @ lane_pressures

    # Matrix of actual observations. All phases are represented by 4 features, so shape
    # is (phase_count, 4).
    real_obs = np.zeros((phase_count, 4), dtype=np.float32)

    # First column -> phase pressures.
    real_obs[:, 0] = phase_pressures

    # Second column -> phase active (1 or 0).
    # Third column -> phase active duration.
    if 0 <= current_phase_idx < phase_count:
        real_obs[current_phase_idx, 1] = 1.0
        real_obs[current_phase_idx, 2] = float(seconds_in_current_phase)

    # Fourth column -> phase transit counts.
    real_obs[:, 3] = transit_detections

    # TODO: Read green times from configuration.
    min_green_time: float = 5
    max_green_time: float = 30

    action_mask = np.ones(phase_count, dtype=np.float32)

    # Mask off all other phases until minimum green has elapsed.
    if seconds_in_current_phase < min_green_time:
        action_mask[:] = 0.0
        action_mask[current_phase_idx] = 1.0

    # Mask off current phase, if maximum green has passed.
    elif seconds_in_current_phase >= max_green_time:
        action_mask[current_phase_idx] = 0.0

    return {
        "real_obs": real_obs,
        "action_mask": action_mask,
    }


def _get_lane_pressure(pressure_config: LanePressureConfig) -> float:
    q_in = pressure_config.incoming_detector.vehicle_count

    weighted_q_out = sum(
        m.theta * m.detector.vehicle_count for m in pressure_config.movements
    )

    total_theta = sum(m.theta for m in pressure_config.movements)

    return (total_theta * q_in) - weighted_q_out


def get_reward(
    current_phase_idx: int,
    pressure_configs: list[LanePressureConfig],
    transit_detections: np.ndarray,
) -> float:
    """Calculate reward based on lane pressures and transit vehicle queues."""
    pressure_penalty = 0.0
    for pressure_config in pressure_configs:
        pressure = _get_lane_pressure(pressure_config)
        pressure_penalty += abs(pressure)

    transit_penalty: float = float(
        np.delete(transit_detections, current_phase_idx, axis=0).sum() * 5,
    )

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
