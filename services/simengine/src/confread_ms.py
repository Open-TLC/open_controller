"""This module provides an object for configuring Open Controller for running
in integrated simulation mode. It will read command line arguments and configuration
file specified in CLI args.
"""

# Copyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

import argparse
import json
from typing import Any

from jsmin import jsmin


class GlobalConf:
    """Open Controller configuration object for runnin integrated simulations.

    This contains configurable options for the simulation, timer, and controller."""

    def __init__(self):
        # Step 1: read the command line params.
        command_line_params = self._read_command_line()

        # Step 2: read configuration from the file specified in command line.
        file_conf = self._read_conf(command_line_params["conf_file"])

        # Step 3: set the initial configuration to the file config.
        conf = file_conf

        # Step 4: remove empty options from command line.
        none_keys = []
        for k, v in command_line_params.items():
            if v is None:
                none_keys.append(k)
        for k in none_keys:
            del command_line_params[k]

        # Step 5: override file options with command line options.
        conf["sumo"].update(command_line_params)

        self.cnf = conf

    def _read_command_line(self) -> dict[str, Any]:
        """Read command line arguments.

        Returns:
            Command line arguments as a dictionary.
        """

        parser = argparse.ArgumentParser()

        parser.add_argument(
            "--conf-file",
            help="Open Controller configuration file (JSON)",
            required=True,
        )

        parser.add_argument(
            "--control-engine-path",
            help="Path to control engine, needed for some special installation setups",
            required=False,
        )

        parser.add_argument(
            "--graph",
            help="If set, run graphical version of sumo",
            action="store_true",
            required=False,
        )

        parser.add_argument(
            "--print-status",
            help="If set, prints status info in every update",
            action="store_true",
            required=False,
        )

        args = parser.parse_args()

        return vars(args)

    def _read_conf(self, filename: str) -> dict[str, Any]:
        """Opens the file and returns values as a dictionary"""
        config: dict[str, Any] = {}
        with open(filename) as json_cnf_file:
            config = json.loads(jsmin(json_cnf_file.read()))

        if len(config.keys()) == 0:
            raise ValueError("No configurations in file: ", filename)

        return config

    def get_controller_params(self):
        print("controller params: ", self.cnf)
        print("keys: ", self.cnf.keys())
        controller_names = list(self.cnf.keys())
        first_controller_name = controller_names[0]
        controller_params = self.cnf[first_controller_name]
        return controller_params
