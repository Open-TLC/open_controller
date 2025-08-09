""" -*- coding: utf-8 -*-
This unti handles the reading of configuration
from file (client_conf.json by default)
"""

# Copyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

import json
import argparse
import sys
from jsmin import jsmin

# Default values
DEFAULT_FILENAME = "client_conf.json"
IMPL_VERSION = "0.1"
SOFTWARE_NAME = "TrafficController"


class GlobalConf:
    "Class for handling all the software configuration (read only)"

    def __init__(self, filename=None):

        # To store command line settings
        self.command_line = {}

        # To store settings given by conf-file
        self.file_conf = {}

        # Combination of file and command line, this is the settings
        # to be used
        # note: this should NOT changed after the initial read
        self.cnf = {}
        self.parser = None
        if not filename:
            # Read conf from command line + given file/default file
            self.set_conf_parameters()
        else:
            # Simply read the params from given file
            self.cnf = self.read_conf(filename)


    def set_conf_parameters(self):
        """Sets up all the conf in self.cnf
        This happens by reading both the command line
        and configuration file. The self.cnf should
        not be tampered with after this"""

        # Step 1: read the command line params
        command_line_params = self.read_command_line()
        self.command_line = vars(command_line_params)

        # Add sumo params as subdictionary, an example
        #self.command_line['sumo'] = {'graph': self.command_line['graph']}

        # Step 2: read conf-file (as defined in command line, if defined)
        if command_line_params.conf_file:
            self.file_conf = self.read_conf(command_line_params.conf_file)
        else:
            self.file_conf = self.read_conf(DEFAULT_FILENAME)

        # Step 3: combine both to CLOBAL_CONF
        self.cnf = self.file_conf

        # print(self.command_line)
        # remove keys not set at command line
        none_keys = []
        for k, v in self.command_line.items():
            if v is None:
                none_keys.append(k)
        for k in none_keys:
            del self.command_line[k]

        self.cnf.update(self.command_line)
        # Note: this will replace file settings with command line
        # Given that they have the same name. Won't work with
        # a more complicated set up (not to be used without conf?)

    def read_command_line(self):
        """Returns parsed command line arguments
        used for client serving data from nats to db
        """
        operation_description = """
        Service for connecting to the NATS reading data, manipulating it
        and inserting the data into a db
        """

        self.parser = argparse.ArgumentParser(
            description=operation_description)

        vers = SOFTWARE_NAME + " v. " + IMPL_VERSION
        self.parser.add_argument('--version', action='version', version=vers)


        self.parser.add_argument('--conf-file',
                                 help='Config file '
                                      '(default: client_conf.json)',
                                 required=False)

        self.parser.add_argument('--graph',
                                 help='If set, run graphical version of sumo',
                                 action='store_true',
                                 required=False)


        self.parser.add_argument('--print-status',
                                 help='If set, prints status info in every update',
                                 action='store_true',
                                 required=False)


        args = self.parser.parse_args()

        return args


    def read_conf(self, file_name):
        """Opens the file and returns values as a dictionary"""
        config = {}
        try:
            with open(file_name) as json_cnf_file:
                config = json.loads(jsmin(json_cnf_file.read()))
        except FileNotFoundError:
            print('File does not exist:', file_name)
            print('Exiting...')
            sys.exit()

        # Should we add sanity check for input?
        return config

    def get_controller_params(self, verbose: bool = False):
        if verbose:
            print('controller params: ', self.cnf)
            print('keys: ', self.cnf.keys())
        controller_names = list(self.cnf.keys())
        first_controller_name = controller_names[0]
        controller_params = self.cnf[first_controller_name]
        return controller_params
    


if __name__ == '__main__':
    print("testing for the confread")
    test_cnf = GlobalConf()
#    test_cnf.set_conf_parameters()

    print(test_cnf.cnf)
