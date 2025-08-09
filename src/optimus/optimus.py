import numpy as np
from stable_baselines3 import SAC
from stable_baselines3.common.env_checker import check_env

from .trafficenv import TrafficEnv  # Make sure this is correct

NUM_LEARNING_EPISODES = 5
NUM_TESTING_EPISODES = 1
STEPS_PER_EPISODE = 1000  # Optional: your env should enforce this internally


def main():
    env = TrafficEnv(conf_root="models/test")

    # Optional: check if your environment follows Gym's API
    print("Checking environment...")
    check_env(env, warn=True)
    print("Environment check successful")

    # Initialize the agent using SAC (actor-critic)
    print("Initializing model...")
    model = SAC("MlpPolicy", env, verbose=1)
    # model = PPO("MlpPolicy", env, verbose=1)
    print("Model initialized!")

    # Train the model
    print("Starting model training...")
    model.learn(
        total_timesteps=STEPS_PER_EPISODE * NUM_LEARNING_EPISODES, progress_bar=True
    )
    print("Model trained!")

    env.reset()

    # Run manually and log episode rewards
    episode_rewards = []

    for ep in range(NUM_TESTING_EPISODES):
        obs, info = env.reset()
        total_reward = 0

        for step in range(STEPS_PER_EPISODE):
            action, _states = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            if terminated or truncated:
                break

        episode_rewards.append(total_reward)
        print(f"Episode {ep + 1}: total reward = {total_reward:.2f}")

        env.save_conf(verbose=True)

    env.close()
    print("\nAverage reward:", np.mean(episode_rewards))


if __name__ == "__main__":
    main()
