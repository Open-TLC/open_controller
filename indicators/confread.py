""" 
This unit handles the reading of traffic_indicators configuration
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
        connectivity = {
            "notes" : "Default connection params",
            "nats" : {
                "server" : DEFAULT_NATS_SERVER,
                "port" : DEFAULT_NATS_PORT
            }
        }
        self.conf['connectivity'] = connectivity

        # No default inputs
        inputs = {}
        self.conf['inputs'] = inputs

        # Outputs
        outputs = {}
        self.conf['outputs'] = outputs

        # Detlogics
        detlogics = {}
        self.conf['detlogics'] = detlogics


       
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

        # We then update the configuration one section at the time,
        # This is needed in order to preserve the default values
        if 'connectivity' in config_from_file:
            self.conf['connectivity'].update(config_from_file['connectivity'])
            if 'nats' in config_from_file['connectivity']:
                self.conf['connectivity']['nats'].update(config_from_file['connectivity']['nats'])

        if 'inputs' in config_from_file:
            self.conf['inputs'].update(config_from_file['inputs'])

        if 'outputs' in config_from_file:
            self.conf['outputs'].update(config_from_file['outputs'])

        if 'detlogics' in config_from_file:
            self.conf['detlogics'].update(config_from_file['detlogics'])


    def set_vals_from_command(self, command_line_params):
        """Sets the values from the command line"""
        # NATS servers
        if command_line_params.nats_server:
            self.conf['connectivity']['nats']['ip'] = command_line_params.nats_server
        if command_line_params.nats_port:
            self.conf['connectivity']['nats']['port'] = command_line_params.nats_port

    

    def get_nats_params(self):
        """Returns the nats parameters (host:port)"""
        if 'connectivity' not in self.conf:
            return None
        if 'nats' not in self.conf['connectivity']:
            return None
        nats_params = self.conf['connectivity']['nats']

        return str(nats_params['server']) + ':' + str(nats_params['port'])

    
    def get_input_params(self):
        """Returns inputs sections"""
        return self.conf['inputs']

    def get_radar_input_params(self):
        """Returns parameters for the radars as a dictionary"""
        radars = {}
        input_params = self.conf['inputs']
        for input_name, params in input_params.items():
            if params['type'] == 'radar':
                radars[input_name] = params
        return radars
    
    def get_outputs(self):
        """Returns the outputs defined in the configuration"""
        outputs = dict(self.conf['outputs'])
        
        # We replace the detlogic function with the params int the detlogics
        for output_name, params in self.conf['outputs'].items():
            if "type" in params:
                if params["type"] == "detlogic":
                    detlogic_function_name = None
                    if "function" in params:
                        detlogic_function_name = params["function"]
                        if detlogic_function_name in self.conf["detlogics"]:
                            outputs[output_name]["function"] = self.conf["detlogics"][detlogic_function_name]
        return outputs

if __name__ == '__main__':
    print("testing for the confread")
    test_cnf = GlobalConf()
    # cnf.set_conf_parameters()

    print(test_cnf.get_json_str(prettyprint=True))
