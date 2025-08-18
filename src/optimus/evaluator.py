import json
import os
import sys
from typing import Any

from stable_baselines3 import PPO, SAC
from stable_baselines3.common.base_class import BaseAlgorithm

from optimus.simengine import SimEngine
from optimus.trafficenv import TrafficEnv

TEST_SIMULATION_ROOT = "models/test"
TEST_MODEL_NAMES = ["ppo_2", "sac_1"]


def main() -> None:
    evaluator = Evaluator(3600)
    for model in TEST_MODEL_NAMES:
        evaluator.add_model(TEST_SIMULATION_ROOT, model)
    evaluator.add_simulation(TEST_SIMULATION_ROOT)

    res = evaluator.evaluate()
    print("Printing evaluations:")
    for r in res.keys():
        print(f"{r}: {round(res[r])}")
    evaluator.save_results(os.path.join(TEST_SIMULATION_ROOT, "out", "eval.json"))


class Evaluator:
    def __init__(self, eval_length_s: int) -> None:
        # Dictionary of model/simulation ID -> cumulative time loss
        self.results: dict[str, float] = {}

        # Evaluation run length in seconds of simulation time
        self.eval_length: int = eval_length_s

        # Dictionary of model ID -> initial Open Controller configuration and optimus model name
        self.models: dict[str, tuple[str, str]] = {}

        # Dictionary of simulation ID -> simulation and Open Controller configuration
        self.sim_confs: dict[int, str] = {}
        self._sim_count: int = 0  # Number for indexing simulations

    def add_model(self, simulation_model_root: str, optimus_model_name: str) -> None:
        self.models[optimus_model_name] = (simulation_model_root, optimus_model_name)

    def add_simulation(self, simulation_model_root: str) -> None:
        # Simulation configuration with Open Controller is loaded from file.
        # This expects that base Open Controller configuration is in "model_root/contr/e3.json"
        self.sim_confs[self._sim_count] = simulation_model_root
        self._sim_count += 1

    def evaluate(self) -> dict[Any, float]:
        """
        evaluate runs simulation for all added models and simulations
        and saves the cumulative time losses to Evaluator

        @return
        dict[str, float]: dictionary with model/simulation ID -> cumulative time loss
        """
        results: dict[Any, float] = {}

        for sim_id in self.sim_confs.keys():
            sim: SimEngine = SimEngine(self.sim_confs[sim_id], collect_time_loss=True)
            step_lenth = sim.conf.cnf["timer"]["time_step"]
            step_count = round(self.eval_length / step_lenth)
            sim.run(step_count)
            total_time_loss: float = sim.total_time_loss
            results[sim_id] = total_time_loss
            sim.close()

        for model_id in self.models.keys():
            sim_root, model_name = self.models[model_id]
            env, model = _load_model(sim_root, model_name)
            step_count = round(self.eval_length / env.step_length_s)

            obs, _ = env.reset()
            for i in range(step_count):
                action, _ = model.predict(obs, deterministic=True)
                obs, reward, _, _, _ = env.step(action)
                if i % 50 == 0:
                    print(f"i: {i} => {action}")
                    print(f"reward = {reward}")
            total_time_loss: float = env.sim_eng.total_time_loss
            results[model_id] = total_time_loss
            env.close()

        self.results = results

        return results

    def save_results(self, result_path: str) -> None:
        with open(result_path, mode="w") as f:
            json.dump(self.results, f, indent=4)


def _load_model(
    simulation_root: str, optimus_model_name: str
) -> tuple[TrafficEnv, BaseAlgorithm]:
    env = TrafficEnv(simulation_root)

    # Trained Optimus model is loaded from a .zip file
    optimus_model_path: str = os.path.join(
        simulation_root, "optimus", (optimus_model_name + ".zip")
    )
    model_type: str = optimus_model_name.split("_")[0]
    model: BaseAlgorithm
    if model_type == "sac":
        model = SAC.load(optimus_model_path)
    elif model_type == "ppo":
        model = PPO.load(optimus_model_path)
    else:
        sys.exit(f"Unknown model type: {model_type}\nTerminating...")

    return env, model


if __name__ == "__main__":
    main()
