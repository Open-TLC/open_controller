import os
import time
from copy import deepcopy
from typing import Any, Optional

import gymnasium as gym
import numpy as np

from simengine.confread_integrated import GlobalConf as SystemConf

from .simengine import SimEngine
from .sumo import get_trips_since


class TrafficEnv(gym.Env):
    def __init__(self, conf_root: str):
        super().__init__()
        self._conf_root = conf_root
        self.system_conf = SystemConf(filename=os.path.join(conf_root, "contr/e3.json"))
        sim_eng = SimEngine(self.system_conf)
        self.sim_eng = sim_eng
        self._last_step_time: float = self.sim_eng.get_current_simulation_time()

        self._step_count: int = 0
        self._teleported: int = 0

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
        self.sim_eng.update_controller(new_controller_conf)

        # Number of simulation steps to run between learning steps
        # 10 steps = 1 s of simulated time
        NUM_OF_STEPS: int = 1800
        self.sim_eng.run(steps=NUM_OF_STEPS)

        # Reward value is calculated from the sum of time losses
        reward: float = self._reward()
        self._last_step_time = self.sim_eng.get_current_simulation_time()

        # Traffic information is read to observation vector
        observation: np.ndarray = self._get_observations()

        # If car's need to teleport, episode is terminated.
        # This tries to teach network to avoid situations
        # where individual vehicles need to wait for
        # extended period's of time
        terminated: bool = False
        if self._teleported < self.sim_eng.teleported:
            # print("Vehicles teleported...")
            terminated = True
            self._teleported = self.sim_eng.teleported

        # Currently environment doesn't have truncated case.
        # This could be implemented in the future to
        # stop simulation if time losses grow rapidly
        truncated: bool = False

        self._step_count += 1
        info_msg = f"step: {self._step_count} completed"

        return observation, reward, terminated, truncated, {"message": info_msg}

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        super().reset(seed=seed)
        self.sim_eng.reset()
        self._last_step_time = self.sim_eng.get_current_simulation_time()
        observation: np.ndarray = self._get_observations()
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
        trips = get_trips_since(self.sim_eng.traci, self._last_step_time)

        res: float = 0
        for trip in trips:
            # FIXME: find actual vehicle types and define transit IDs as a list
            if trip.type == "transit":
                res -= trip.time_loss * 10
            else:
                res -= trip.time_loss

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
        signal_groups: dict[str, Any] = new.cnf["controller"]["signal_groups"]
        for group in signal_groups:
            for param in OPTIMIZED_CONTROLLER_PARAMS:
                val: float = 100 * float(1 + action[i])
                if val < 0:
                    val = 0
                signal_groups[group][param] = val
                i += 1

        extenders: dict[str, Any] = new.cnf["controller"]["extenders"]
        for extender in extenders:
            for param in OPTIMIZED_EXTENDER_PARAMS:
                val: float = 100 * float(1 + action[i])
                if val < 0:
                    val = 0
                extenders[extender][param] = 100 * float(action[i])
                i += 1

        return new

    def _get_action_dim(self) -> int:
        controller_count = len(self.system_conf.cnf["controller"]["signal_groups"])
        extender_count = len(self.system_conf.cnf["controller"]["extenders"])

        controller_params = len(OPTIMIZED_CONTROLLER_PARAMS)
        extender_params = len(OPTIMIZED_EXTENDER_PARAMS)

        val_count: int = (
            controller_count * controller_params + extender_count * extender_params
        )

        return val_count


OPTIMIZED_CONTROLLER_PARAMS: list[str] = [
    "min_green",
    "min_red",
    "max_green",
]

OPTIMIZED_EXTENDER_PARAMS: list[str] = [
    "ext_threshold",
    "time_discount",
]
