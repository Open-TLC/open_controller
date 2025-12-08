"""The stand alone clockwrk module for running the traffic indicators.

This component will connect to gieven data sources and calculate the traffic indicators.

"""
# Copyright 2023 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

SOFTWARE_NAME = "Open Controller Traffic Indicators"
IMPL_VERSION = "0.1"

RADAR_TEST_TOPIC = "radar.270.1.objects_port.json"
CONF_FILE = "models/testmodel/indicators.json"

import asyncio
from nats.aio.client import Client as NATS
import argparse
from confread import GlobalConf
from radar import Radar
from fusion2 import FieldOfView
from detector import Detector
from group import Group
import pandas as pd
import re

# Note: should be in a separate file in the end
class SensorTwin:
    """A class for containing copy of the sensor data"""

    def __init__(self):
        self.radars = {}
        self.detectors = {}
        self.groups = {}
        self.inputs = []
        self.outputs = []
        self.fovs = {} # Fields of View
        

    def __str__(self):
        ret_str = "Sensor twin:\n"
        ret_str += "   Radars: {}\n".format(len(self.radars))
        ret_str += "   Detectors: {}\n".format(len(self.detectors))
        ret_str += "   Groups: {}\n".format(len(self.groups))
        return ret_str
    
    #
    # Adding the streams
    #
    
    # RADARS
    def add_radar_streams(self, radar_dict):
        """Adds a radar streams to the twin"""
        # For tewin, this creates the radar objects
        for name, params in radar_dict.items():
            radar = Radar(name, params)
            self.radars[name] = radar

        # This assigns the radars to the field of view
        # For generating the outputs and manipulationg the data
        for fov in self.fovs.values():
            fov.assign_radars(self.radars)
        print(self.fovs)

    #DETECTORS
    def add_detector_streams(self, detector_dict):
        """Adds a detector streams to the twin"""
        # For twin, this creates the Detector objects
        for name, params in detector_dict.items():
            detector = Detector(name, params)
            self.detectors[name] = detector

        # This assigns the detectors to the field of view
        # For generating the outputs and manipulationg the data
        for fov in self.fovs.values():
            fov.assign_detectors(self.detectors)

    # GROUPS
    def add_group_streams(self, group_dict):
        """Adds a group streams to the twin"""
        for name, params in group_dict.items():
            group = Group(name, params)
            self.groups[name] = group
        
        # This assigns the detectors to the field of view
        # For generating the outputs and manipulationg the data
        for fov in self.fovs.values():
            fov.assign_groups(self.groups)


    def assign_counting_blocks(self):
        """Assigns the counting blocks to the detectors"""
        for fov in self.fovs.values():
            fov.assign_counting_blocks()

    def add_field_of_views(self, fov_dict):
        """Adds a field of view to the twin"""
        for name, params in fov_dict.items():
            fov = FieldOfView(name, params)
            self.fovs[name] = fov
    
    
    def get_all_configured_nats_subs(self):
        """Returns all nats subscriptions"""
        subs = []
        # RADARS
        for radar in self.radars.values():
            sub_params = radar.get_nats_sub_params()
            if sub_params:  
                subs.append(sub_params)
        # DETS
        for detector in self.detectors.values():
            sub_params = detector.get_nats_sub_params()
            if sub_params:  
                subs.append(sub_params)
        
        # GROUPS
        for group in self.groups.values():
            sub_params = group.get_nats_sub_params()
            if sub_params:  
                subs.append(sub_params)

        return subs

    def get_cleanup_tasks(self):
        """Returns cleanup tasks for each sensor"""
        tasks = []
        # RADARS
        for radar in self.radars.values():
            tasks.append(radar.cleanup_old_data)
        # DETS
        for detector in self.detectors.values():
            tasks.append(detector.cleanup_old_data)
        
        return tasks
    
    def get_send_messages_tasks(self):
        """Returns the send queue tasks"""
        tasks = []
        # Fields of view
        for fov in self.fovs.values():
            tasks.append(fov.send_nats_messages)
       

        # Detectors (testing)
        for detector in self.detectors.values():
            tasks.append(detector.send_data) 
        #for radar in self.radars.values():
        #    tasks.append(radar.send_queues)
        return tasks

async def main():
    command_line_params = read_command_line()
    config = GlobalConf(command_line_params=command_line_params, conf=command_line_params.conf)

    sensor_twin = SensorTwin()
    
    # Adds the field of views
    # Note: this has to be done _before_ adding the streams
    # Adding the streams also assigns them to the field of views
    fov_params = config.get_view_outputs()
    sensor_twin.add_field_of_views(fov_params)
    
    # Adds the radar, detector and group streams
    # These are used for subscribing to the data
    # And sroting it to the Radar and Detector objects
    radar_stream_params = config.get_radar_stream_params()
    sensor_twin.add_radar_streams(radar_stream_params)
    
    det_stream_params = config.get_det_stream_params()
    sensor_twin.add_detector_streams(det_stream_params)

    group_stream_params = config.get_group_stream_params()
    sensor_twin.add_group_streams(group_stream_params)

    sensor_twin.assign_counting_blocks()

    # Deubug
    #print("STREAM   PARAMS")
    #print(det_stream_params)
    #print("RADAR STEAMS")
    #print(config.get_radar_stream_params())

    #print("Logic OUTPUTS")
    #print(config.get_detlogic_outputs())
    #exit()

    # Nats connection
    nats_connection_params = config.get_nats_params()
    nats = NATS()
    await nats.connect(nats_connection_params)

    # Sub to all subjects in config
    all_subs = sensor_twin.get_all_configured_nats_subs()
    #print("All subs:", all_subs)
    for sub in all_subs:
        await nats.subscribe(sub['subject'], cb=sub['callback'])

    # Add cleanup tast into asuncio loop for each sensor
    tasks = sensor_twin.get_cleanup_tasks()
    for task in tasks:
        asyncio.create_task(task())

    # For sending the queues
    tasks = sensor_twin.get_send_messages_tasks()
    for task in tasks:
        asyncio.create_task(task(nats))

    while True:
        await asyncio.sleep(1)
        print('***********************TRAFFIC_INDICATORS*****************************')
        fovs_out = "Fovs:"

        df = pd.DataFrame(columns=["Name", "Age", "Occupation"])

        fovs_out = "Groups: "
        for name, fov in sensor_twin.fovs.items():    
            grp = fov.group_name
            grp_num = int(re.findall(r"\d+", grp)[0])
            if grp_num < 10:
                add = " "
            else:
                add =""
            fovs_out += " | " + add + str(grp_num)
        fovs_out += " | "
        print(fovs_out)

        fovs_out = "States: "
        for name, fov in sensor_twin.fovs.items():    
            sig_state = fov.group.substate
            if sig_state == None:
                fovs_out += " |   " + sig_state
            else:
                fovs_out += " |  " + sig_state
        fovs_out += " | "
        print(fovs_out)

        fovs_out = "Queues: "
        for name, fov in sensor_twin.fovs.items():  
            obj_cnt = len(fov.get_objects_in_all_lanes())
            grp = fov.group_name
            grp_num = int(re.findall(r"\d+", grp)[0])
            if obj_cnt < 10:
                add = " "
            else:
                add =""
            fovs_out += " | " + add + str(obj_cnt)
        fovs_out += " | "
        print(fovs_out)

        print('______________________________________________________________________')  

        
        



def read_command_line():
    """Returns parsed command line arguments
    """

    operation_description = """
    Runs the sumo in real time and relays the detector and group states
    to a nats-server
    """
    parser = argparse.ArgumentParser(
        description=operation_description)

    vers = SOFTWARE_NAME + " v. " + IMPL_VERSION
    parser.add_argument('--version', action='version', version=vers)

    parser.add_argument('--conf',
                                help='Configuration parameters '
                                    '(default: default.json)',
                                required=False)

   
    parser.add_argument('--nats-server',
                                help='Nats server address ',
                                required=False)
    parser.add_argument('--nats-port',
                                help='Nats server port ',
                                required=False)
    
    args = parser.parse_args()

    return args

if __name__ == "__main__":
    asyncio.run(main())

ls