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
        inputs_streams = {}
        self.conf['input_streams'] = inputs_streams

        # Detlogics
        detlogics = {}
        self.conf['detlogics'] = detlogics

        # Inputs
        inputs = {}
        self.conf['inputs'] = inputs

        # Lanes
        lanes = {}
        self.conf['lanes'] = lanes

        # Outputs
        outputs = {}
        self.conf['outputs'] = outputs



       
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

        if 'input_streams' in config_from_file:
            self.conf['input_streams'].update(config_from_file['input_streams'])

        if 'detlogics' in config_from_file:
            self.conf['detlogics'].update(config_from_file['detlogics'])

        if 'inputs' in config_from_file:
            self.conf['inputs'].update(config_from_file['inputs'])

        if 'lanes' in config_from_file:
            self.conf['lanes'].update(config_from_file['lanes'])

        if 'outputs' in config_from_file:
            self.conf['outputs'].update(config_from_file['outputs'])



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

    def get_radar_stream_params(self):
        """Returns parameters for the input radars stream as a dictionary"""
        radars = {}
        input_params = self.conf['input_streams']
        for input_name, params in input_params.items():
            if params['type'] == 'radar':
                radars[input_name] = params
        return radars
    
    # TODO: this fails if reading is done more than once
    def get_det_stream_params(self):
        """Returns parameters for the detector input streams as a dictionary"""
        # In this case we have to first find all the detector names that are defined
        # in the inputs section
        if 'dets' not in self.conf['inputs']:
            return {}
        input_dets = self.conf['inputs']['dets']
        for det_name, params in input_dets.items():
            stream_name = params.get('stream', None)
            if stream_name:
                if stream_name in self.conf['input_streams']:
                    input_dets[det_name]['stream'] = self.conf['input_streams'][stream_name]
                    # We combine stream channes from the input name
                    # and the stream name (prefix)
                    channel = self.conf['input_streams'][stream_name]['nats_subject']
                    det_subject_name = input_dets[det_name]['name']
                    if channel[-1] == '*':
                        channel = channel[:-1] # Remove star
                    channel = channel + det_subject_name
                    # deep copy the values and not change the original
                    new_dict = dict(input_dets[det_name]['stream'])
                    new_dict['nats_subject'] = channel
                    input_dets[det_name]['stream'] = new_dict
                    #input_dets[det_name]['stream']['nats_subject'] = channel
                else:
                    print(f"Error: stream {stream_name} not found in input_streams")
        return input_dets


    def get_group_stream_params(self):
        """Returns the group stream parameters"""
        if 'groups' not in self.conf['inputs']:
            return {}
        input_groups = self.conf['inputs']['groups']
        for group_name, params in input_groups.items():
            stream_name = params.get('stream', None)
            if stream_name:
                if stream_name in self.conf['input_streams']:
                    input_groups[group_name]['stream'] = self.conf['input_streams'][stream_name]
                    # We combine stream channes from the input name
                    # and the stream name (prefix)
                    channel = self.conf['input_streams'][stream_name]['nats_subject']
                    group_subject_name = input_groups[group_name]['group']
                    if channel[-1] == '*':
                        channel = channel[:-1]
                    channel = channel + group_subject_name
                    # deep copy the values and not change the original
                    new_dict = dict(input_groups[group_name]['stream'])
                    new_dict['nats_subject'] = channel
                    input_groups[group_name]['stream'] = new_dict
                else:
                    print(f"Error: stream {stream_name} not found in input_streams")
        return input_groups
   

    # NOTE: not correct
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


    
    
    #
    # Detlogic outputs
    #

    def get_detlogic_outputs(self):
        """Returns the detlogic outputs"""
        outputs = self.conf['outputs']
        detlogic_outputs = {}
        for output_name, params in outputs.items():
            if "type" in params:
                if params["type"] == "detlogic":
                    detlogic_outputs[output_name] = params
        # Get the detlogic function
        for output_name, params in detlogic_outputs.items():
            if "function" in params:
                detlogic_outputs[output_name]["function"] = self.get_detlogc_function(params["function"])   
        return detlogic_outputs


    def get_detlogc_function(self, function_name):
        """Returns the detlogic function from detlogics section"""
        # Handling the missing params
        if not 'detlogics' in self.conf:
            print ("Error: detlogics not found in conf")
            return None
        if function_name in self.conf['detlogics']:
            detlogic_function_params = self.conf['detlogics'][function_name]
        else:
            print(f"Error: detlogic function {function_name} not found in detlogics")
            return None
        # Return according to the type
        if "type" in detlogic_function_params:
            if detlogic_function_params["type"] == "two_det_switch":
                return self.get_twodet_switch_params(detlogic_function_params)        
        return None

    def get_twodet_switch_params(self, params):
        """Returns the two detector switch parameters"""
        detectors = params.get('detectors', {})
        if not detectors:
            print("Error: detectors not found in two_det_switch")
            return None
        if "request" in detectors:
            detectors["request"] = self.get_detector_input_params(detectors["request"])
        if "clear" in detectors:
            detectors["clear"] = self.get_detector_input_params(detectors["clear"])
        params['detectors'] = detectors
        return params

    # 
    # Wiew output functions, these handle the group views (sensor fusion in the future)
    #

    def get_view_outputs(self):
        """Returns outputs for group view, note that this not only rerutns the
        outputs but also searches params for lanes, radar outputs and etc"""
        outputs = self.conf['outputs']
        view_outputs = {}
        for output_name, params in outputs.items():
            if "type" in params:
                if params["type"] == "grp_view":
                    view_outputs[output_name] = params
                    lanes = params.get('lanes', [])
                    lane_params = [] # Will be filled with actual conf
                    for l in lanes:
                        l_params = self.get_lane_params(l) # this reads "lanes section"
                        if l_params:
                            lane_params.append(l_params)
                    view_outputs[output_name]['lanes'] = lane_params
        return view_outputs

    def get_lane_params(self, lane_name):
        """Returns the lane parameters (from the lanes section)"""
        lane_params = None
        for param_lane_name, params in self.conf['lanes'].items():
            if param_lane_name == lane_name:
                lane_params = params
                # These read the params from the inputs section
                # For radars
                rad_lanes = params.get('radar_lanes', [])
                radar_lane_params = {}
                for r_lane in rad_lanes:
                    radar_lane_params[r_lane] = self.get_radar_input_params(r_lane)
                lane_params['radar_lanes'] = radar_lane_params
                # For in dets
                in_dets = params.get('in_dets', [])
                in_det_params = {}
                for in_det in in_dets:
                    in_det_params[in_det] = self.get_detector_input_params(in_det)
                lane_params['in_dets'] = in_det_params
                # For out dets
                out_dets = params.get('out_dets', [])
                out_det_params = {}
                for out_det in out_dets:
                    out_det_params[out_det] = self.get_detector_input_params(out_det)
                lane_params['out_dets'] = out_det_params

        return lane_params

    # read from "inputs section"
    def get_radar_input_params(self, radar_name):
        """Returns parameters for the radars as a dictionary"""
        radars_section = self.conf['inputs'].get('rad_lanes', {})
        radar_params = {}
        for param_radar_name, params in radars_section.items():
            if param_radar_name == radar_name:
                radar_params = params
                #if 'stream' in params:
                    # This reads the params from the input_streams section
                #    radar_params['stream'] = self.get_input_stream_params(params['stream'])
        return radar_params

    # read from "inputs section"
    def get_detector_input_params(self, detector_name):
        """Returns parameters for the detectors as a dictionary"""
        detectors_section = self.conf['inputs'].get('dets', {})
        detector_params = {}
        for param_detector_name, params in detectors_section.items():
            if param_detector_name == detector_name:
                detector_params = params
        return detector_params

    # Note: currently not used
    def get_input_stream_params(self, input_name):
        """Returns the input stream parameters"""
        input_params = self.conf['input_streams']
        for param_input_name, params in input_params.items():
            if param_input_name == input_name:
                return params
        return None

if __name__ == '__main__':
    print("testing for the confread")
    test_cnf = GlobalConf()
    # cnf.set_conf_parameters()

    print(test_cnf.get_json_str(prettyprint=True))
