""" -*- coding: utf-8 -*-
This unit handles the reading of configuration
from file, it also defines the default values if conf file is not
provided
"""

import json
import sys
from jsmin import jsmin

# Default values
# Simulator
DEFAULT_NATS_SERVER = "localhost"
DEFAULT_NATS_PORT = 4222
DEFAULT_SUMO_CONFIG = "sumo_config.json"

# Default values
# Outputs
DEFAULT_SUBJECT_STAT_DETECTORS = "detector.status" # Prefix 
DEFAULT_SUBJECT_STAT_GROUPS = "group.status" # Prefix 



class GlobalConf:
    "Class for handling all the software configuration (read only)"

    def __init__(self, command_line_params=None, conf=None):
        # Combination of file and command line
        # We will 1) set default values, 2) read conf file, 3) read command line
        # Each step will overwrite the previous one (if params are set)
        
        print(command_line_params)        
        # Step 1: Set default values
        self.set_default_values()
        # Step 2: Read conf file
        if conf:
            self.set_vals_from_conf(conf)
        # Step 3: Read command line
        if command_line_params:
            self.set_vals_from_command(command_line_params)

    def __str__(self):
        return str(self.conf)


    def get_json_str(self, prettyprint=False):
        """Returns the configurariton as a string of json
        it prettyprint is set to True, it will be formatted
        """
        if prettyprint:
            return json.dumps(self.conf, indent=4)
        else:
            return json.dumps(self.conf)
        

    def set_default_values(self):
        """
            Sets the default values thisi is intented to be run before
            we read the params from a file and command line
        """
        self.conf = {}
        simparams = {
            "notes" : "Default simulation params",
            "sumo_conf" : DEFAULT_SUMO_CONFIG,
            "graphics": False,
            "nats" : {
                "server" : DEFAULT_NATS_SERVER,
                "port" : DEFAULT_NATS_PORT
            }
        }
        det_outputs = {
            "type": "detector",
            "trigger": "never",
            "det_mapping_mode": "direct",
            "det_map": {},
            "topic_prefix": DEFAULT_SUBJECT_STAT_DETECTORS,
            "notes" : "Default output params"
        }
        sig_outputs = {
            "type": "signalhead",
            "trigger": "never",
            "signal_mapping_mode": "direct",
            "topic_prefix": DEFAULT_SUBJECT_STAT_GROUPS,
            "signal_map": {}
        }

        outputs = {
            "det_outputs": det_outputs,
            "sig_outputs": sig_outputs
        }
        self.conf['simulation'] = simparams

        self.conf['outputs'] = outputs

        # No default inputs
        inputs = {}
        self.conf['inputs'] = inputs

       
    def set_vals_from_conf(self, filename):
        """Opens the conf-file and update the self.conf"""
        config_from_file = {}

        try:
            with open(filename) as json_cnf_file:
                config_from_file = json.loads(jsmin(json_cnf_file.read()))
        except FileNotFoundError:
            print('File does not exist:', filename)
            print('Exiting...')
            sys.exit()

        # We then update the configuration one section at the time
        # simulation
        if 'simulation' in config_from_file:
            self.conf['simulation'].update(config_from_file['simulation'])
            if 'nats' in config_from_file['simulation']:
                self.conf['simulation']['nats'].update(config_from_file['simulation']['nats'])
        # Radars. Note: needed by output config so we need to set it first
        if 'radars' in config_from_file:
            self.conf['radars'] = config_from_file['radars']

        # outputs
        if 'outputs' in config_from_file:
            if 'det_outputs' in config_from_file['outputs']:
                self.conf['outputs']['det_outputs'].update(config_from_file['outputs']['det_outputs'])
            if 'sig_outputs' in config_from_file['outputs']:
                self.conf['outputs']['sig_outputs'].update(config_from_file['outputs']['sig_outputs'])    
            if 'rad_outputs' in config_from_file['outputs']:
                self.set_rad_outputs(config_from_file['outputs']['rad_outputs'])
        # inputs
        if 'inputs' in config_from_file:
            if 'sig_inputs' in config_from_file['inputs']:
                self.conf['inputs']['sig_inputs'] = config_from_file['inputs']['sig_inputs']


    def set_rad_outputs(self, rad_config):
        """This function will fetch the radar values in separate structure and add them to the outputs"""
        if not 'radars' in self.conf:
            print("No radar values in the configuration")
            return
        radars = {}
        for rad_tag in rad_config['radars']:
            if rad_tag in self.conf['radars']:
                radars[rad_tag] = self.conf['radars'][rad_tag]
            else:
                print("No radar with tag ", rad_tag, " in the radar configuration")
        rad_config['radars'] = radars
        self.conf['outputs']['rad_outputs'] = rad_config      

    def set_vals_from_command(self, command_line_params):
        """Sets the values from the command line"""
        # NATS servers
        if command_line_params.nats_server:
            self.conf['simulation']['nats']['ip'] = command_line_params.nats_server
        if command_line_params.nats_port:
            self.conf['simulation']['nats']['port'] = command_line_params.nats_port

        if 'graph' in command_line_params:
            self.conf['simulation']['graphics'] = command_line_params.graph
        
        if 'sumo_conf' in command_line_params:
            self.conf['simulation']['sumo_conf'] = command_line_params.sumo_conf

    

    def get_nats_params(self):
        """Returns the nats parameters (host:port)"""
        return str(self.conf['simulation']['nats']['ip']) + ':' + str(self.conf['simulation']['nats']['port'])

    def get_sumo_config(self):
        """Returns the sumo config file"""
        return self.conf['simulation']['sumo_conf']
    
    def get_output_params(self):
        """Returns outputs sections"""
        return self.conf['outputs']
    
    def get_input_params(self):
        """Returns inputs sections"""
        return self.conf['inputs']

    
    def graph_mode(self):
        """Returns the graph mode"""
        return self.conf['simulation']['graphics']

    def det_statuses_every_update(self):
        """Returns true if det statuses are sent every update"""
        if self.conf['outputs']['det_outputs']['trigger'] == "every_update":
            return True
        else:
            return False
        
    def send_det_statuses(self):
        """Returns true if det statuses are sent at all"""
        if self.conf['outputs']['det_outputs']['trigger'] == "never":
            return False
        else:
            return True
    
    def send_sig_statuses(self):
        """Returns true if det statuses are sent at all"""
        if self.conf['outputs']['sig_outputs']['trigger'] == "never":
            return False
        else:
            return True

    def get_radar_polygons(self):
        """Returns the radar polygons"""
        radars = {}
        for rad_id, rad_vals in self.conf['outputs']['rad_outputs']['radars'].items():
            if 'area_of_interest' in rad_vals:
                radars[rad_id] = rad_vals['area_of_interest']
        return radars

if __name__ == '__main__':
    print("testing for the confread")
    test_cnf = GlobalConf()
    # cnf.set_conf_parameters()

    print(test_cnf.get_json_str(prettyprint=True))
