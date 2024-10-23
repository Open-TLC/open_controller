# -*- coding: utf-8 -*-
"""The stand alone clockwrk module for running the controller

This module runs the controller in real time and relays the messages
to NATS server in localhost. This is intended to be used with a real contoller
in the field or alternatively with a simulation model.
"""
# Copyright 2023 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

SOFTWARE_NAME = "TrafficController"
IMPL_VERSION = "0.2"

DEFAULT_NATS_SERVER = "localhost"
DEFAULT_NATS_PORT = 4222


DEFAULT_CHANNEL = "detector.*.*"

DETECTOR_CHANNEL = "detector.sumo"
DEFAULT_CONF_FILE = "testmodel/nats_controller.json"
CACHE_CONTROLLER_CONF_FILE = "../cache/model.json"
#DEFAULT_CONF_FILE = "../models/JS270_TB_kari/JS270_flowmed_T3B5max.json"

STATUS_CHANNEL_PREFIX = "clockwork.status" # output
NETWORK_CHANNEL_PREFIX = "clockwork.network"
CLOCKWORK_CONF_CHANNEL = "clockwork.conf"
COMMAND_CHANNEL = "clockwork.command" # input
REQUEST_SUBSTATES = ['E','F']

import os
import asyncio
from nats.aio.client import Client as NATS
from nats.errors import TimeoutError, NoRespondersError
import json
from datetime import datetime, timezone
import argparse

from confread import GlobalConf
from signal_group_controller import PhaseRingController
from timer import Timer


BEGININNG_ALL_RED_TIME = 10 # seconds


class DataDistributor:
    """Distributes the data to and from
    the controller """

    def __init__(self, controller, conf, nats, system_timer):
        self.nats = nats
        self.controller = controller
        self.name = conf['name']
        self.conf = conf
        self.system_timer = system_timer
        # DET input
        self.det_mapping = self.get_det_channel_mapping(conf['detectors'], controller) 
        # Group output
        self.group_mapping = self.get_group_control_channel_mapping(conf['signal_groups'], controller)
        # Request message input
        self.group_request_mapping = self.get_request_channel_mapping(conf['signal_groups'], controller)
        
        # Group status input
        self.group_status_mapping = self.get_group_status_channel_mapping(conf['signal_groups'], controller)
        self.group_status_storage = ControllerGroupStatusRequests()
        
        print("Group mapping:", self.group_mapping)
        # We store these for the case we want to trigger message sending based on the change of the status
        # I.e. "change" mode under nats -section in the conf file
        self.group_states = {}
        for group in self.group_mapping:
            self.group_states[group] = None
        self.run_updates = True
        print("*******************")
        for group in self.group_status_mapping.values():
            print(group.name, " index:", group.controller_index)
        print("*******************")
        print(self.group_status_mapping)
        print("*******************")
        #exit()

    def __str__(self) -> str:
        return str(self.det_mapping)

    def get_det_channel_mapping(self,detector_conf, controller):
        "Returns a dictionary of all the channels and their corresponding detectors (as list)"
        mapping = {}
        #all_dets = controller.get_all_detectors()
        all_dets = controller.ext_dets + controller.req_dets
        for det in detector_conf:
            if "channel" in detector_conf[det]:
                channel = detector_conf[det]["channel"]
                list_of_dets_for_the_channel = []
                for d in all_dets:
                    if d.name == det:
                        list_of_dets_for_the_channel.append(d)
                if not channel in mapping:
                    mapping[channel] = list_of_dets_for_the_channel
                else:
                    mapping[channel].extend(list_of_dets_for_the_channel)
            else:
                print("Warning, no channel for detector:", det)
        return mapping


    # Note: this channel is defined in the conf file
    # The following mappings (request and status mappings) are derived from this
    # FIXME likely we should onlu define the group number and use that instead of channel as string
    def get_group_control_channel_mapping(self, group_conf, controller):
        "Returns a dictionary of all the channels and their corresponding groups (as list)"
        mapping = {}
        for group in group_conf:
            print("Group:", group_conf[group])
            if "channel" in group_conf[group]:
                channel = group_conf[group]["channel"]
                for c_group in controller.groups:
                    if c_group.group_name == group:
                        mapping[channel] = c_group
        return mapping


    def get_request_channel_mapping(self, group_conf, controller):
        "Returns request channel mapping"
        # Unlike detector and group channels, these are not defined in the conf file
        # instead we modify the group channel names for this purpose
        group_mapping = self.get_group_control_channel_mapping(group_conf, controller)
        mapping = {}
        
        for channel in group_mapping:
            # We replace the "control" in channel name with "request"
            request_channel_name = channel.replace("control", "request")
            mapping[request_channel_name] = group_mapping[channel]
        return mapping
    
    def get_group_status_channel_mapping(self, group_conf, controller):
        "Returns request channel mapping"
        # Unlike detector and group channels, these are not defined in the conf file
        # instead we modify the group channel names for this purpose
        group_mapping = self.get_group_control_channel_mapping(group_conf, controller)
        mapping = {}
        
        for channel in group_mapping:
            # We replace the "control" in channel name with "request"
            request_channel_name = channel.replace("control", "status")
            mapping[request_channel_name] = group_mapping[channel]
        return mapping

    def detector_message_to_controller(self, msg, channel):
        msg_dict = json.loads(msg)
        det_list = []
        if channel in self.det_mapping:
            for det in self.det_mapping[channel]:
                #print("Det:", det, "loop_on", msg_dict["loop_on"])
                det.loop_on = msg_dict["loop_on"]
                #print("Channel:", channel, "Det:", det)
                det_list.append(self.det_mapping[channel])
        #print("Setting detectors", det_list, " with message:", msg_dict)

    def group_request_message_to_controller(self, msg, channel):
        "Handsles the group request messages"
        msg_dict = json.loads(msg)
        if channel in self.group_request_mapping:
            # If request true, we set the request to the group
            if msg_dict["request"]:
                self.group_request_mapping[channel].request_green=True
                print("Setting request for group:", self.group_request_mapping[channel].group_name, " to:", msg_dict["request"])

    def group_status_message_request_to_controller(self, msg, channel):
        "This function reads the status messages and if the status changes from non request status to request status, it sets the request to the group"
        if self.group_status_storage.request_changed_on(msg, channel):
            self.group_status_mapping[channel].request_green=True
            print("Setting request for group:", self.group_status_mapping[channel].group_name)


    def get_det_channels(self):
        return self.det_mapping.keys()

    def get_group_request_channels(self):
        return self.group_request_mapping.keys()

    def get_group_status_channels(self):
        return self.group_status_mapping.keys()


    # For handling the initial states
    def group_state_has_changed(self, status, channel):
        if not channel in self.group_states:
            self.group_states[channel] = status
        
        if self.group_states[channel] == None:
            self.group_states[channel] = status


        if self.group_states[channel]['green'] == status['green']:
            return False
        else:
            self.group_states[channel] = status
            return True

    # Note: the commands are currently strings, this should me transformed to json
    async def handle_command(self, msg):
        """
            This function handles the commands sent to the controller
            These are at this stage mostly data requests
        """
        subject = msg.subject
        reply = msg.reply
        command = msg.data.decode().strip()
    
        print("Received a command:", command)
        if command=="get_status":
            print(self.get_status_as_dict())
    
        if command=="get_network":
            print("Sending the network status")
            network_channel = NETWORK_CHANNEL_PREFIX + "." + self.name
            #await nats.publish(network_channel, json.dumps(self.get_network_status()).encode())
            await self.nats.publish(network_channel, "NETWORK".encode())
        
        if command=="stop":
            print("Stopping the controller")
            self.run_updates = False
        if command=="start":
            print("Starting the controller")
            self.system_timer.reset_time_step()
            self.run_updates = True

        if command=="save_conf":
            print("Saving the conf file")
            self.controller.save_conf()
            self.controller.read_conf() # maybe removed later
            await msg.respond("OK".encode())

    async def handle_conf_request(self, msg):
        """
            This callback function handles the conf requests
        """
        print("Received a conf request:", msg)
        command = msg.data.decode().strip()
        if command=="get_conf":
            conf = self.controller.get_conf_as_dict()['controller']
            await msg.respond(json.dumps(conf).encode()) 
        else:   
            self.controller.process_new_conf(json.loads(msg.data.decode().strip()))
            await msg.respond("OK".encode())


# FIX ME: the nats functions  should be in the DataDistributor class
async def main(conf_filename=None, set_controller_requests=False):
    command_line = read_command_line()
    print("Command line:", command_line)

    nats_server = command_line.nats_server + ":" + str(command_line.nats_port)
    if not command_line.conf_file:
        print("No conf file given, using default", DEFAULT_CONF_FILE)
        conf_filename = DEFAULT_CONF_FILE
    else:
        conf_filename = command_line.conf_file

    unit_cnf = GlobalConf(filename=conf_filename)
    sys_cnf = unit_cnf.cnf

    # Timer based on the conf file, will be given to the controller(s) as param
    timer_params = sys_cnf['timer']
    system_timer = Timer(timer_params)


    print("Running controller with conf", sys_cnf)
    
    # Note, in the future we might have multiple controllers
    # However, this is not implemented yet
    controller_filename = None
    


    # Whe then check if cache conf is found and if so, override the controller conf
    if os.path.exists(CACHE_CONTROLLER_CONF_FILE):
        print("Using cached controller conf fil_e at:", CACHE_CONTROLLER_CONF_FILE)
        controller_filename = CACHE_CONTROLLER_CONF_FILE
        # Note: this is not used now

    # To be added, override by the command lin

    #controlles_conf = GlobalConf(filename=controller_filename)
    #controller_cnf = controlles_conf.cnf['controller']

    controller_cnf = sys_cnf['controller']
    
    traffic_controller = PhaseRingController(controller_cnf, system_timer)

    nats= NATS()
    distributor = DataDistributor(traffic_controller, controller_cnf, nats, system_timer)

    
    # These should be read from the conf file FIXME
    await nats.connect(nats_server)

    # Note: we could assign a different callback for each channel (might be more efficient)
    async def det_message_handler(msg):
        subject = msg.subject
        reply = msg.reply
        data = msg.data.decode()
        distributor.detector_message_to_controller(data, subject)


    
    channels = distributor.get_det_channels()
    #We subscribe all the DET channels defined in the conf
    for channel in channels:
        await nats.subscribe(channel, cb=det_message_handler)
        print("Subscribed to det channel", channel)
    
    # We subscribe to the group request channels
    async def group_request_message_handler(msg):
        subject = msg.subject
        reply = msg.reply
        data = msg.data.decode()
        print("Received group request message:", data)
        distributor.group_request_message_to_controller(data, subject)
    
    channels = distributor.get_group_request_channels()
    for channel in channels:
        await nats.subscribe(channel, cb=group_request_message_handler)
        print("Subscribed to group request channel", channel)


    # We subscribe to the group status channels
    # These are used for updating the request of groups 
    # based on groups status of the physical controller
    async def group_status_message_handler(msg):
        subject = msg.subject
        reply = msg.reply
        data = msg.data.decode()
        distributor.group_status_message_request_to_controller(data, subject)
    
    channels = distributor.get_group_status_channels()
    if set_controller_requests:
        print("Setting controller requests based on the group statuses")
        for channel in channels:
            await nats.subscribe(channel, cb=group_status_message_handler)
            print("Subscribed to group status channel", channel)


    
    # We subscribe to the command channel
    await nats.subscribe(COMMAND_CHANNEL, cb=distributor.handle_command)

    # Thos is for returning the conf file to the client
    await nats.subscribe(CLOCKWORK_CONF_CHANNEL, cb=distributor.handle_conf_request)
    
    #try:
    #    await nats.request(CLOCKWORK_CONF_CHANNEL, b'', timeout=0.5)
    #except NoRespondersError:
    #    print("no responders")

    # When we start we will send an all red message to the groups
    for channel in distributor.group_mapping:
        group_message = get_group_control_message(distributor.group_mapping[channel], channel)
        await nats.publish(channel, json.dumps(group_message).encode())
    # Wait for 15 seconds for everyone to go green
    print("Waiting for the groups to go red, for ", BEGININNG_ALL_RED_TIME, " seconds")
    time_waited = 0
    while time_waited < BEGININNG_ALL_RED_TIME:
        for channel in distributor.group_mapping:
            group_message = get_group_control_message(distributor.group_mapping[channel], channel)
            print(group_message)
            await nats.publish(channel, json.dumps(group_message).encode())
        await asyncio.sleep(5)
        time_waited += 5

    
    #await asyncio.sleep(BEGININNG_ALL_RED_TIME)
    print("Starting the controller")


    status_channel = STATUS_CHANNEL_PREFIX + "." + controller_cnf['name']
    while True:
        
        # If run updates is off, we just sleep and wait for the next command
        if not distributor.run_updates:
            await asyncio.sleep(system_timer.get_next_time_step())
            continue
        traffic_controller.tick()
        system_timer.tick()
        # For printing the status of the controller if requested in conf
        #if sys_cnf['sumo']['print_status']:
        #    print(traffic_controller.get_control_status())
        
        # status will be sent to its own channer every time step
        controller_stat = traffic_controller.get_status_as_dict()
        if sys_cnf['nats']['mode'] == 'update':
            await nats.publish(status_channel, json.dumps(controller_stat).encode())
        
        if sys_cnf['nats']['mode'] == 'change':
            await nats.publish(status_channel, json.dumps(controller_stat).encode())
        


        # For sending the groups statuses to the nats server if requested in conf
        if sys_cnf['nats']['mode'] == 'update':
            for channel in distributor.group_mapping:
                #group_status = distributor.group_mapping[channel].get_status()
                group_message = get_group_control_message(distributor.group_mapping[channel], channel)
                await nats.publish(channel, json.dumps(group_message).encode())
                #print("Published group status:", group_message, " to channel:", channel)

        if sys_cnf['nats']['mode'] == 'change':
            for channel in distributor.group_mapping:
                group_message = get_group_control_message(distributor.group_mapping[channel], channel)
                stat = group_status_from_msg(group_message)
                if distributor.group_state_has_changed(stat, channel):
                    await nats.publish(channel, json.dumps(group_message).encode())
                    print("Published group status:", group_message, " to channel:", channel)

        # Debugging the time drift remove later
        # print(system_timer.aggregate_time_drift)        
        await asyncio.sleep(system_timer.get_next_time_step())


def get_group_control_message(group, channel):
    """Returns a message for the group control as a dictionary format
    Takes group object as an input and returns"""
    msg = {}
    msg["id"] = channel
    current_time = str(datetime.now()).replace(" ", "T") + "Z"
    msg["tstamp"] = current_time
    msg["substate"] = group.get_grp_state()
    msg["group"] = int(channel.split(".")[-1])
    msg["green"] = (not group.group_red())
    return msg


def detections_to_controller(msg, channel, detector_mapping):
    "Sets the detector statuses in controller based on controller configuration and message"
    # We extract the sumo id from the message
    msg_json = json.loads(msg)
    if channel in detector_mapping:
        for det in detector_mapping[channel]:
            print("Setting detector", det.name, " with message:", msg_json)

def group_status_from_msg(msg):
    "Returns the group status (a dict of state and substate) from the message"
    status = {}
    status["green"] = msg["green"]
    status["substate"] = msg["substate"]
    return status


def read_command_line():
    """Returns parsed command line arguments
    used for client serving data from nats to db
    """
    

    operation_description = """
    Service for connecting to the NATS reading data, manipulating it
    and inserting the data into a db
    """
    parser = argparse.ArgumentParser(
        description=operation_description)

    vers = SOFTWARE_NAME + " v. " + IMPL_VERSION
    parser.add_argument('--version', action='version', version=vers)


    parser.add_argument('--conf-file',
                                help='Config file '
                                    '(default: client_conf.json)',
                                required=False)


    parser.add_argument('--print-status',
                                help='If set, prints status info in every update',
                                action='store_true',
                                required=False)

    parser.add_argument('--set-controller-requests',
                                help='This is set if we want the open controller to follow the requests set by the physical controller',
                                action='store_true',
                                required=False)
    
    parser.add_argument('--nats-server',
                                help='Nats server address '
                                    '(default: localhost)',
                                default=DEFAULT_NATS_SERVER,
                                required=False)
    parser.add_argument('--nats-port',
                                help='Nats server port '
                                    '(default: 4222)',
                                default=DEFAULT_NATS_PORT,
                                required=False)
    
    args = parser.parse_args()

    return args
 

class ControllerGroupStatusRequests:
    "This is a class for containing current requests of the groups in the physial controller"
    def __init__(self):
        self.group_requests = {}

    def request_changed_on(self, msg, channel):
        "Processes the status message, stores the req status and returns true if the request has changed to true"
        
        # From string to dict
        status = json.loads(msg)
        if status['substate'] in REQUEST_SUBSTATES:
            request = True
        else:
            request = False

        # This is not the firs message for the group
        if channel in self.group_requests:
            # If the request has changed to true, we set the request to the group
            if (not self.group_requests[channel]) and request:
                print("Request has started fo the group at channel:", channel)
                return True
        # Add or update the request info for the group/channel
        self.group_requests[channel] = request
        return False

if __name__ == "__main__":
    print("Running the controller as NATS client")
    asyncio.run(main())
    exit()
    if 'conf_file' in command_line:
        print("Using conf file:", command_line.conf_file)
        asyncio.run(main(conf_filename=command_line.conf_file, set_controller_requests=command_line.set_controller_requests))
    else:
        print("Using default conf file")
        asyncio.run(main(conf_filename="testmodel/nats_controller.json"))