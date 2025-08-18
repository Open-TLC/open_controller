import os
import time
import unittest

import numpy as np

from optimus.simengine import SimEngine
from optimus.trafficenv import TrafficEnv
from simengine.confread_integrated import GlobalConf as SystemConf

TEST_CONF_ROOT = "models/test"

sys_cnf = SystemConf(filename=os.path.join(TEST_CONF_ROOT, "contr/e3.json"))


class TestOptimus(unittest.TestCase):
    def test_simengine(self):
        try:
            sim_eng = SimEngine(sys_cnf)

            sim_eng.run(100)

            sim_eng.close()
        except Exception:
            self.fail("test_simengine raised unexpected exception!")

    def test_trafficenv(self):
        try:
            env = TrafficEnv(TEST_CONF_ROOT)
            # env.reset()

            dim = env._get_action_dim()
            action = np.zeros(shape=(dim,), dtype=np.float32)
            start = time.time()
            NUM_OF_STEPS: int = 10
            for _ in range(NUM_OF_STEPS):
                _, _, terminated, _, _ = env.step(action)
                if terminated:
                    self.fail("test_trafficenv: simulation terminated")

            time_taken_ms: int = round((time.time() - start) * 1000)
            print(f"{NUM_OF_STEPS} steps took {time_taken_ms} milliseconds")

            env.close()
        except Exception:
            self.fail("test_trafficenv raised unexpected exception!")


if __name__ == "__main__":
    unittest.main()
