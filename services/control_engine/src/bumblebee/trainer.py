import argparse
import asyncio
import datetime
import os
from typing import Any, cast

import numpy as np
import ray
import yaml
from ray.rllib.algorithms.ppo import PPOConfig
from ray.rllib.core.rl_module.multi_rl_module import MultiRLModuleSpec
from ray.rllib.core.rl_module.rl_module import RLModuleSpec
from ray.rllib.utils.typing import AgentID, EpisodeType, MultiAgentPolicyConfigDict
from ray.tune.registry import register_env
from torch.utils.tensorboard import SummaryWriter

from .configuration import TrainerConf
from .frap_network import FRAPMaskedPPORLModule
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
            conf_dict = yaml.safe_load(f)
    except FileNotFoundError as e:
        raise ValueError(f"Configuration file not found at '{conf_filename}'.") from e
    except yaml.YAMLError as e:
        raise ValueError(f"Configuration file contains invalid YAML syntax: {e}") from e

    conf = TrainerConf(conf_dict)

    _train_multi_agent(conf, tensorboard_dir, model_file)


def _train_multi_agent(
    conf: TrainerConf,
    tensorboard_dir: str | None,
    model_file: str,
) -> None:
    print("Initializing Multi-Agent Environment...")

    ray_tmp_path = os.path.expanduser("~/ray_tmp")
    os.makedirs(ray_tmp_path, exist_ok=True)
    ray.init(ignore_reinit_error=True, _temp_dir=ray_tmp_path)

    register_env("traffic_env", _env_creator)

    dummy_env = _env_creator({"conf": conf})

    if dummy_env.observation_spaces is None or dummy_env.action_spaces is None:
        raise ValueError(
            "Environment spaces are not initialized. Ensure observation_spaces "
            "and action_spaces are populated in your TraffiEnv __init__.",
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

    policy_ids = [str(pid) for pid in raw_policies]

    # Configure RLModule specifications for every agent/policy.
    rl_module_spec = MultiRLModuleSpec(
        rl_module_specs={
            pid: RLModuleSpec(
                module_class=FRAPMaskedPPORLModule,
                model_config={
                    "hidden_dim": getattr(conf, "hidden_dim", 32),
                    "embed_dim": getattr(conf, "embed_dim", 16),
                },
            )
            for pid in policy_ids
        },
    )

    # Build algorithm configuration.
    config = (
        PPOConfig()
        .environment(env="traffic_env", env_config={"conf": conf})
        .framework("torch")
        .multi_agent(
            policies=policies,
            policy_mapping_fn=_map_agent_to_policy,
        )
        .rl_module(rl_module_spec=rl_module_spec)
        .env_runners(num_env_runners=0)
        .training(
            num_epochs=4,
            train_batch_size_per_learner=3600,
            entropy_coeff=0.01,
        )
    )

    print("Building Algorithm...")
    algo = config.build_algo()

    writer: SummaryWriter | None = None
    if tensorboard_dir:
        timestr = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        logdir = os.path.join(tensorboard_dir, f"run_{timestr}")
        os.makedirs(logdir, exist_ok=True)
        writer = SummaryWriter(log_dir=logdir)

    print("Starting model training...")

    for i in range(conf.total_steps):
        print(f"Step {i}")
        result = algo.train()
        if writer:
            _write_results(writer, i, result)

    if writer:
        writer.close()
    print("Model trained!")

    if model_file:
        algo.save(checkpoint_dir=model_file)
        print(f"Multi-Agent Model Checkpoint folder saved to: {model_file}")

    ray.shutdown()


def _write_results(writer: SummaryWriter, step: int, result: dict[str, Any]) -> None:
    agent_rewards: dict[str, np.float64] | None = result["env_runners"].get(
        "agent_episode_returns_mean",
    )

    if agent_rewards is not None:
        mean_reward = sum(agent_rewards.values()) / len(
            agent_rewards,
        )
        writer.add_scalar("Rewards/Mean_Reward", mean_reward, step)

        for aid in agent_rewards:
            writer.add_scalar(f"Rewards/Agent_{aid}", float(agent_rewards[aid]), step)


def _env_creator(env_config):
    conf: TrainerConf = env_config["conf"]
    local_simengine = SimEngine(conf.simengine)
    return asyncio.run(
        TrafficEnv.create(
            local_simengine,
            conf.traffic_env,
            conf.controllers,
            conf.detectors,
        ),
    )


def _map_agent_to_policy(agent_id: AgentID, _: EpisodeType) -> str:
    return str(agent_id)


if __name__ == "__main__":
    _train()
