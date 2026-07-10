import argparse
import datetime
import json
import os
from typing import Any, cast

import gymnasium
import numpy as np
import ray
from gymnasium.wrappers import RecordEpisodeStatistics
from ray.rllib.algorithms.dqn import DQNConfig
from ray.rllib.algorithms.ppo import PPOConfig
from ray.rllib.utils.typing import AgentID, EpisodeType, MultiAgentPolicyConfigDict
from ray.tune.registry import register_env
from stable_baselines3 import A2C, DQN, PPO
from stable_baselines3.common.base_class import BaseAlgorithm
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.env_checker import check_env
from torch.utils.tensorboard import SummaryWriter

from .configuration import TrainerConf
from .multi_trafficenv import MultiTrafficEnv
from .simengine import SimEngine
from .trafficenv import TrafficEnv


def _train() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--conf-file",
        help="Bumblebee trainer configuration file (json)",
        required=True,
    )

    parser.add_argument(
        "--model-file",
        help="File to save the trained model (zip)",
        required=False,
    )

    parser.add_argument(
        "--tensorboard",
        help="Tensorboard log directory",
        required=False,
    )

    args = parser.parse_args()
    conf_filename: str = args.conf_file  # Configuration file location.
    model_file: str = args.model_file  # Target location for trained model.
    tensorboard_dir: str = args.tensorboard  # Tensorboard log directory.

    try:
        with open(conf_filename) as f:
            conf_dict = json.load(f)
    except FileNotFoundError as e:
        raise ValueError(f"Configuration file not found at '{conf_filename}'.") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Configuration file contains invalid JSON syntax: {e}") from e

    conf = TrainerConf(conf_dict)

    if len(conf.controllers) == 1:
        _train_single_agent(conf, tensorboard_dir, model_file)
    else:
        _train_multi_agent(conf, tensorboard_dir, model_file)


def _train_single_agent(
    conf: TrainerConf,
    tensorboard_dir: str | None,
    model_file: str,
) -> None:
    print("Initializing Single-Agent Environment...")
    simengine = SimEngine(conf.simengine)

    env = TrafficEnv(simengine, conf.traffic_env, conf.controllers[0])

    # If tensorboard directory exists, environment is wrapped in a logging wrapper.
    if tensorboard_dir:
        env = RecordEpisodeStatistics(env)

    print("Environment created!")
    print("Checking environment...")
    check_env(env)
    print("Environment checked!")

    print("Starting model training...")
    model = _create_model(env, conf, tensorboard_dir)

    model.learn(
        total_timesteps=conf.total_steps,
        progress_bar=True,
        callback=_TrafficStatsCallback(),
    )
    print("Model trained!")

    if model_file:
        model.save(model_file)
        print("Model saved!")


def _train_multi_agent(
    conf: TrainerConf,
    tensorboard_dir: str | None,
    model_file: str,
) -> None:
    print("Initializing Multi-Agent Environment...")

    if conf.algorithm == "a2c":
        raise ValueError("A2C is not configured for Multi-Agent execution.")

    ray_tmp_path = os.path.expanduser("~/ray_tmp")
    os.makedirs(ray_tmp_path, exist_ok=True)
    ray.init(ignore_reinit_error=True, _temp_dir=ray_tmp_path)

    register_env("multi_traffic_env", _env_creator)

    dummy_env = _env_creator({"conf": conf})

    if dummy_env.observation_spaces is None or dummy_env.action_spaces is None:
        raise ValueError(
            "Environment spaces are not initialized. Ensure observation_spaces "
            "and action_spaces are populated in your MultiTrafficEnv __init__.",
        )

    raw_policies = {
        aid: (
            None,
            dummy_env.observation_spaces[aid],
            dummy_env.action_spaces[aid],
            {},
        )
        for aid in dummy_env.possible_agents
    }

    policies = cast(MultiAgentPolicyConfigDict, raw_policies)

    if conf.algorithm == "ppo":
        config = PPOConfig()
    elif conf.algorithm == "dqn":
        config = DQNConfig()
    else:
        raise ValueError(f"Unknown Multi-Agent algorithm: {conf.algorithm}")

    config.environment(env="multi_traffic_env", env_config={"conf": conf})
    config.framework("torch")

    config = config.multi_agent(
        policies=policies,
        policy_mapping_fn=_map_agent_to_policy,
    )

    config = config.env_runners(num_env_runners=0)

    config.training(
        num_epochs=4,
        train_batch_size_per_learner=3600,
        entropy_coeff=0.01,
        lr=[[0, 0.0005], [200, 0.0001], [600, 0.00002]],
        grad_clip=0.1,
        grad_clip_by="norm",
    )

    print("Building Multi-Agent Model Configuration...")
    algo = config.build_algo()

    writer: SummaryWriter | None = None
    if tensorboard_dir:
        timestr = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        logdir = os.path.join(tensorboard_dir, f"run_{timestr}")
        os.makedirs(logdir, exist_ok=True)
        writer = SummaryWriter(log_dir=logdir)

    print("Starting Multi-Agent model training...")

    for i in range(conf.total_steps):
        print(f"Step {i}")
        result = algo.train()
        if writer:
            _write_results(writer, i, result)

    if writer:
        writer.close()
    print("Multi-Agent Model trained!")

    if model_file:
        algo.save(checkpoint_dir=model_file)
        print(f"Multi-Agent Model Checkpoint folder saved to: {model_file}")

    ray.shutdown()


def _write_results(writer: SummaryWriter, step: int, result: dict[str, Any]) -> None:
    mean_reward: float | None = float(result["env_runners"].get("episode_return_mean"))
    agent_rewards: dict[str, np.float64] | None = result["env_runners"].get(
        "agent_episode_returns_mean",
    )

    if mean_reward is not None:
        writer.add_scalar("Rewards/Mean_Reward", mean_reward, step)

    if agent_rewards is not None:
        for aid in agent_rewards:
            writer.add_scalar(f"Rewards/Agent_{aid}", float(agent_rewards[aid]), step)


def _env_creator(env_config):
    conf: TrainerConf = env_config["conf"]
    local_simengine = SimEngine(conf.simengine)
    return MultiTrafficEnv(local_simengine, conf.traffic_env, conf.controllers)


def _map_agent_to_policy(agent_id: AgentID, episode: EpisodeType) -> str:
    return str(agent_id)


def _create_model(
    env: gymnasium.Env,
    conf: TrainerConf,
    tensorboard_dir: str | None,
) -> BaseAlgorithm:
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

    return model


class _TrafficStatsCallback(BaseCallback):
    def _on_step(self):
        infos = self.locals["infos"]

        for info in infos:
            if "traffic" in info:
                traffic = info["traffic"]

                self.logger.record("traffic/teleported", traffic.get("teleported"))
                self.logger.record("traffic/finished", traffic.get("finished"))

                self.logger.record(
                    "traffic/avg_travel_time",
                    traffic.get("avg_travel_time"),
                )

            if "metrics" in info:
                self.logger.record("metrics/reward", info["metrics"].get("reward"))

        return True


if __name__ == "__main__":
    _train()
