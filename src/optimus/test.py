import os
import unittest

from optimus.simengine import SimEngine
from simengine.confread_integrated import GlobalConf as SystemConf

TEST_CONF_ROOT = "models/test"


class TestOptimus(unittest.TestCase):
    def test_simengine(self):
        try:
            sys_cnf = SystemConf(filename=os.path.join(TEST_CONF_ROOT, "contr/e3.json"))

            sim_eng = SimEngine(sys_cnf)

            sim_eng.run()

            sim_eng.close()
        except Exception:
            self.fail("test_simengine raised unexpected exception!")


if __name__ == "__main__":
    unittest.main()
