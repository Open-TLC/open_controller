import os
import sys
import time

from stable_baselines3 import PPO, SAC
from stable_baselines3.common.base_class import BaseAlgorithm
from stable_baselines3.common.env_checker import check_env

from .trafficenv import TrafficEnv

CONF_ROOT = os.path.join("models", "test")

TRAINING_TIMESTEPS = 500_000

MODEL_TYPE = "sac"


def main():
    env = TrafficEnv(conf_root=CONF_ROOT)

    print("Checking environment...")
    check_env(env, warn=True)
    print("Environment check successful")

    model_name: str = MODEL_TYPE + "_" + time.strftime("%d%m%H%M")

    print("Initializing model...")
    model: BaseAlgorithm
    if MODEL_TYPE == "sac":
        model = SAC("MlpPolicy", env, verbose=1)
    elif MODEL_TYPE == "ppo":
        model = PPO("MlpPolicy", env, verbose=1)
    else:
        sys.exit(f"Unknown MODEL_TYPE: {MODEL_TYPE}\nTerminating...")
    print("Model initialized!")

    # Train the model
    print("Starting model training...")
    model.learn(total_timesteps=TRAINING_TIMESTEPS)
    print("Model trained!")

    env.close()

    model_path: str = os.path.join(CONF_ROOT, "optimus", (model_name + ".zip"))
    model.save(model_path)
    print("Model saved to:", model_path)


if __name__ == "__main__":
    main()
