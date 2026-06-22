import argparse
import json

from stable_baselines3 import DQN
from stable_baselines3.common.env_checker import check_env

from .configuration import TrainerConf
from .simengine import SimEngine
from .trafficenv import TrafficEnv


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--conf-file", help="Bumblebee trainer configuration file (JSON)", required=True
    )

    parser.add_argument(
        "--model-file", help="File to save the trained model", required=True
    )

    args = parser.parse_args()
    conf_filename: str = args.conf_file  # Configuration file location.
    model_file: str = args.model_file  # Target location for trained model.

    try:
        with open(conf_filename, mode="r") as f:
            conf_dict = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise ValueError(f"Configuration file could not be read or is invalid: {e}")

    conf = TrainerConf(conf_dict)

    simengine = SimEngine(conf.simengine)
    env = TrafficEnv(simengine, conf.traffic_env)
    print("Environment created!")

    print("Checking environment...")
    check_env(env)
    print("Environment checked!")

    print("Starting model training...")
    model = DQN("MlpPolicy", env, verbose=1)
    model.learn(total_timesteps=conf.total_steps, progress_bar=True)
    print("Model trained!")

    model.save(model_file)
    print("Model saved!")


if __name__ == "__main__":
    main()
