import argparse
import json

from gymnasium.wrappers import RecordEpisodeStatistics
from stable_baselines3 import DQN, PPO
from stable_baselines3.common.base_class import BaseAlgorithm
from stable_baselines3.common.callbacks import BaseCallback
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
    env = RecordEpisodeStatistics(env)
    print("Environment created!")

    print("Checking environment...")
    check_env(env)
    print("Environment checked!")

    print("Starting model training...")
    model: BaseAlgorithm
    if conf.algorithm == "dqn":
        model = DQN("MlpPolicy", env, tensorboard_log="./tensorboard/")
    elif conf.algorithm == "ppo":
        model = PPO("MlpPolicy", env, tensorboard_log="./tensorboard/")
    else:
        raise ValueError("Unknown RL algorithm: ", conf.algorithm)

    model.learn(
        total_timesteps=conf.total_steps,
        progress_bar=True,
        callback=TrafficStatsCallback(),
    )
    print("Model trained!")

    model.save(model_file)
    print("Model saved!")


class TrafficStatsCallback(BaseCallback):
    def _on_step(self):
        infos = self.locals["infos"]

        for info in infos:
            if "traffic" in info:
                traffic = info["traffic"]

                self.logger.record("traffic/teleported", traffic.get("teleported"))

                self.logger.record(
                    "traffic/avg_travel_time", traffic.get("avg_travel_time")
                )

        return True


if __name__ == "__main__":
    main()
