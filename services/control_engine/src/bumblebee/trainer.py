import argparse
import json

import ray
from gymnasium.wrappers import RecordEpisodeStatistics
from ray.rllib.algorithms.dqn import DQNConfig
from ray.rllib.algorithms.ppo import PPOConfig
from ray.rllib.env.wrappers.pettingzoo_env import ParallelPettingZooEnv
from ray.tune.registry import register_env
from stable_baselines3 import A2C, DQN, PPO
from stable_baselines3.common.base_class import BaseAlgorithm
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.env_checker import check_env

from .configuration import TrainerConf
from .multi_trafficenv import MultiTrafficEnv
from .simengine import SimEngine
from .trafficenv import TrafficEnv


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--conf-file", help="Bumblebee trainer configuration file (json)", required=True
    )

    parser.add_argument(
        "--model-file", help="File to save the trained model (zip)", required=False
    )

    parser.add_argument(
        "--tensorboard", help="Tensorboard log directory", required=False
    )

    args = parser.parse_args()
    conf_filename: str = args.conf_file  # Configuration file location.
    model_file: str = args.model_file  # Target location for trained model.
    tensorboard_dir: str = args.tensorboard  # Tensorboard log directory.

    try:
        with open(conf_filename, mode="r") as f:
            conf_dict = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise ValueError(f"Configuration file could not be read or is invalid: {e}")

    conf = TrainerConf(conf_dict)

    simengine = SimEngine(conf.simengine)

    if conf.traffic_env.multi_agent:
        print("Initializing Multi-Agent Environment...")

        if conf.algorithm == "a2c":
            raise ValueError("A2C is not configured for Multi-Agent execution.")

        ray.init(ignore_reinit_error=True)

        base_env = MultiTrafficEnv(simengine, conf.traffic_env, conf.controllers)

        register_env(
            "multi_traffic_env",
            lambda _: ParallelPettingZooEnv(
                MultiTrafficEnv(simengine, conf.traffic_env, conf.controllers)
            ),
        )

        policies = {
            aid: (
                None,
                base_env.observation_spaces[aid],
                base_env.action_spaces[aid],
                {},
            )
            for aid in base_env.possible_agents
        }

        if conf.algorithm == "ppo":
            config = PPOConfig()
        elif conf.algorithm == "dqn":
            config = DQNConfig()
        else:
            raise ValueError(f"Unknown Multi-Agent algorithm: {conf.algorithm}")

        config = (
            config.environment(env="multi_traffic_env")
            .framework("torch")
            .multi_agent(
                policies=policies,
                policy_mapping_fn=lambda agent_id, episode, **kwargs: str(agent_id),
            )
        )

        print("Building Multi-Agent Model Configuration...")
        algo = config.build_algo()

        print("Starting Multi-Agent model training...")
        current_steps = 0

        while current_steps < conf.total_steps:
            results = algo.train()
            current_steps = results["timesteps_total"]

        print("Multi-Agent Model trained!")

        if model_file:
            algo.save(checkpoint_dir=model_file)
            print(f"Multi-Agent Model Checkpoint folder saved to: {model_file}")

        ray.shutdown()

    else:
        print("Initializing Single-Agent Environment...")
        env = TrafficEnv(simengine, conf.traffic_env, conf.controllers[0])

        # If tensorboard directory exists, environment is wrapped in a logging wrapper.
        if tensorboard_dir != "":
            env = RecordEpisodeStatistics(env)

        print("Environment created!")
        print("Checking environment...")
        check_env(env)
        print("Environment checked!")

        print("Starting model training...")
        model: BaseAlgorithm
        if conf.algorithm == "dqn":
            model = DQN(
                "MlpPolicy",
                env,
                tensorboard_log=(tensorboard_dir if tensorboard_dir else None),
            )
        elif conf.algorithm == "ppo":
            model = PPO(
                "MlpPolicy",
                env,
                tensorboard_log=(tensorboard_dir if tensorboard_dir else None),
            )
        elif conf.algorithm == "a2c":
            model = A2C(
                "MlpPolicy",
                env,
                tensorboard_log=(tensorboard_dir if tensorboard_dir else None),
            )
        else:
            raise ValueError("Unknown RL algorithm: ", conf.algorithm)

        model.learn(
            total_timesteps=conf.total_steps,
            progress_bar=True,
            callback=TrafficStatsCallback(),
        )
        print("Model trained!")

        if model_file:
            model.save(model_file)
            print("Model saved!")


class TrafficStatsCallback(BaseCallback):
    def _on_step(self):
        infos = self.locals["infos"]

        for info in infos:
            if "traffic" in info:
                traffic = info["traffic"]

                self.logger.record("traffic/teleported", traffic.get("teleported"))
                self.logger.record("traffic/finished", traffic.get("finished"))

                self.logger.record(
                    "traffic/avg_travel_time", traffic.get("avg_travel_time")
                )

            if "metrics" in info:
                self.logger.record("metrics/reward", info["metrics"].get("reward"))

        return True


if __name__ == "__main__":
    main()
