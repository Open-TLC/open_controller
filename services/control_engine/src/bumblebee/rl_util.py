import numpy as np
from stable_baselines3 import DQN, PPO
from stable_baselines3.common.base_class import BaseAlgorithm

from services.control_engine.src.detectors.area_detector import AreaDetector


def get_observation(
    current_phase_idx: int, detectors: list[AreaDetector]
) -> np.ndarray:
    """Get observation in Bumblebee standard format.

    Args:
        current_phase_idx: The index of the controllers current phase.
        detectors: Detectors from which to get data from.

    Returns:
        Detector readings and phase index in a numpy array.
    """
    obs_list: list[float] = []
    for detector in detectors:
        obs_list.append(detector.vehicle_count())

    obs_list.append(current_phase_idx)

    return np.array(obs_list, dtype=np.float32)


def get_detector_readings(detectors: list[AreaDetector]) -> list[dict[str, float]]:
    """Get detector readings from area detectors.

    Args:
        detectors: Detectors from which to get data from.

    Returns:
        Traffic state as a list of dictionaries
            where the key is the parameter name.
    """

    # TODO: We should subscribe to the detector data
    # rather than retrieve it individually every step.

    readings: list[dict[str, float]] = []
    for detector in detectors:
        reading: dict[str, float] = {
            "vehicle_count": detector.vehicle_count(),
            "average_speed": detector.average_speed(),
            "average_time_loss": detector.average_time_loss(),
        }
        readings.append(reading)

    return readings


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
