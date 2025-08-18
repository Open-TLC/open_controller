import os
import time
from copy import deepcopy
from typing import Any, Optional

import gymnasium as gym
import numpy as np

from simengine.confread_integrated import GlobalConf as SystemConf

from .simengine import SimEngine


class TrafficEnv(gym.Env):
    def __init__(self, conf_root: str, step_simulation_length_s: int = 60):
        super().__init__()
        self._conf_root = conf_root
        self.system_conf = SystemConf(filename=os.path.join(conf_root, "contr/e3.json"))
        sim_eng = SimEngine(conf_root, collect_time_loss=True)
        self.sim_eng = sim_eng

        self._print_status = self.system_conf.cnf["sumo"]["print_status"]
        self.step_length_s = step_simulation_length_s
        self._step_length: int = round(
            step_simulation_length_s / self.system_conf.cnf["timer"]["time_step"]
        )

        self._step_count: int = 0
        self._num_teleported: int = 0

        self._observation_dim = self._get_observation_dim()
        self._action_dim = self._get_action_dim()

        self.observation_space = gym.spaces.Box(
            low=0, high=1000, shape=(self._observation_dim,), dtype=np.float32
        )
        self.action_space = gym.spaces.Box(
            low=-1, high=1, shape=(self._action_dim,), dtype=np.float32
        )

    def step(self, action: np.ndarray):
        # Signal controller is updated based on action vector
        new_controller_conf: SystemConf = self._action_vector_to_config(action)
        self.system_conf = new_controller_conf
        self.sim_eng.update_controller_extenders(self.system_conf)

        self.sim_eng.run(steps=self._step_length)

        # Reward value is calculated from the sum of time losses
        reward: float = self._reward()

        # Traffic information is read to observation vector
        observation: np.ndarray = self._get_observations()

        # If car's need to teleport, episode is terminated.
        # This tries to teach network to avoid situations
        # where individual vehicles need to wait for
        # extended period's of time
        terminated: bool = False
        if self._num_teleported < self.sim_eng.teleported:
            terminated = True
            self._num_teleported = self.sim_eng.teleported
            reward -= 1000 * self._num_teleported
            if self._print_status:
                print(f"cars teleported: {self._num_teleported}")

        # Currently environment doesn't have truncated case.
        # This could be implemented in the future to
        # stop simulation if time losses grow rapidly
        truncated: bool = False

        self._step_count += 1
        info_msg = f"step: {self._step_count} completed"

        if self._print_status:
            print(f"step {self._step_count} completed")
            print("reward was", round(reward))

        return observation, reward, terminated, truncated, {"message": info_msg}

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        super().reset(seed=seed)
        self.sim_eng.close()
        self.sim_eng = SimEngine(self._conf_root, collect_time_loss=True)
        observation: np.ndarray = self._get_observations()
        self._teleported = 0
        self._step_count = 0
        info_msg = "environment reset successfully"
        return observation, {"message": info_msg}

    def render(self):
        raise NotImplementedError

    def close(self):
        self.sim_eng.close()

    def save_conf(self, verbose: bool = False) -> None:
        """
        save_conf is used to save current system configuration to a file
        """

        dest_file: str = os.path.join(
            self._conf_root, "contr", time.strftime("%d%m%H%M") + ".json"
        )
        self.system_conf.write_conf(dest_file)
        if verbose:
            print(f"conf saved to:{dest_file}")

    def _reward(self) -> float:
        if len(self.sim_eng.last_run_losses) == 0:
            return 0
        res: float = 0
        for loss in self.sim_eng.last_run_losses:
            res -= loss**2
        res = res / len(self.sim_eng.last_run_losses)
        return res

    def _get_observations(self) -> np.ndarray:
        e1_readings, e3_readings = self.sim_eng.get_detector_readings()

        result = np.ndarray(shape=(self._observation_dim,), dtype=np.float32)

        i = 0
        for reading in e1_readings:
            result[i] = reading[0]
            result[i + 1] = reading[1]
            i += 2

        for reading in e3_readings:
            result[i] = reading[0]
            result[i + 1] = reading[1]
            i += 2

        return result

    def _get_observation_dim(self) -> int:
        e1_readings, e3_readings = self.sim_eng.get_detector_readings()
        val_count: int = len(e1_readings) * 2 + len(e3_readings) * 2
        return val_count

    def _action_vector_to_config(self, action: np.ndarray) -> SystemConf:
        new: SystemConf = deepcopy(self.system_conf)

        i = 0

        extenders: dict[str, Any] = new.cnf["controller"]["extenders"]
        for extender in extenders:
            for param in OPTIMIZED_EXTENDER_PARAMS:
                # This maps the values to 0-100
                new_value: float = 50 * (1 + float(action[i]))
                extenders[extender][param] = new_value
                i += 1

        new.cnf["controller"]["extenders"] = extenders
        return new

    def _get_action_dim(self) -> int:
        extender_count = len(self.system_conf.cnf["controller"]["extenders"])

        extender_params = len(OPTIMIZED_EXTENDER_PARAMS)

        val_count: int = extender_count * extender_params

        return val_count


OPTIMIZED_EXTENDER_PARAMS: list[str] = [
    "ext_threshold",
    "time_discount",
]
