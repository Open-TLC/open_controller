# -*- coding: utf-8 -*-
"""The simulatione engine for the SUMO simulation

This module runs the sumo in real time and relays the detector and group states
to a nats-server (in localhost or given address)
"""
# Copyright 2023 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

import os
import sys
from datetime import datetime
import asyncio
import argparse
from nats.aio.client import Client as NATS
import json
from timer import Timer
from confread import GlobalConf
from outputs import DetStorage, GroupStorage, RadarStorage


SOFTWARE_NAME = "SUMO Simulation enngine"
IMPL_VERSION = "0.1"

# We define class for the output types
OUTPUT_TYPES = {
    "detector": DetStorage,
    "group": GroupStorage,
    "radar": RadarStorage
}



GREEN_SUBSTATES = ['1', '2', '3', '4', '5', '6', '7', '8', '9']

# This will need:
# export PYTHONPATH=$PYTHONPATH:/usr/share/sumo/tools

# Alternatively:
# we need to import python modules from the $SUMO_HOME/tools directory
if 'SUMO_HOME' in os.environ:
    SUMO_TOOLS = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(SUMO_TOOLS)
    import traci
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")


# One of these is choden with the command line parameter
SUMO_BIN_GRAPH = "sumo-gui"
SUMO_BIN_NO_GRAPH = "sumo"

TIMER_PARAMS = {
    "time_step": 0.1,
    "real_time_multiplier": 1.0
}

# Chosen with the command line parameter
GROUP_CHANNEL_STATUS = "group.status.*.*" #DEBUG
GROUP_CHANNEL_CONTROL = "group.control"

DET_CHANNEL_PREFIX = "detector.status" # This i for (physical) controller
#DET_CHANNEL_PREFIX = "detector.status" # For testing
GROUP_CHANNEL_PREFIX = "group.status"
# For testing the request updates
#GROUP_CHANNEL_PREFIX = "group.status"

# From control messages
#GROUP_CONTROL_CHANNEL = "group.control.*.*"

# Implied from the status messages
GROUP_CONTROL_CHANNEL = "group.status.*.*"

class SumoNatsInterface:
    """This class handles the communication between the sumo and the nats server"""
    
    def __init__(self):
        self.system_timer = Timer(TIMER_PARAMS)
        self.set_up_the_params()


    def set_up_the_params(self):
        """Sets the parameters for the interface based on command line and conf file"""
        # The command line params are set here
        command_line_params = read_command_line()
        self.config = GlobalConf(command_line_params=command_line_params, conf=command_line_params.conf)

        # After this all the configuration is in the self.config"
        self.nats_server = self.config.get_nats_params()
        self.sumo_file = self.config.get_sumo_config()
        # Graphical UI for SUMO
        #if command_line_params.graph:
        if self.config.graph_mode():
            self.sumo_bin=SUMO_BIN_GRAPH
        else:
            self.sumo_bin=SUMO_BIN_NO_GRAPH


        # Datasources
        self.ds_each_update = []
        self.ds_change_update = []

        # Setting up the outputs
        all_outputs = self.config.get_output_params()
        for configuration in all_outputs.values():
            output_storage = OUTPUT_TYPES[configuration["type"]](configuration)
            if configuration["trigger"] == "update":
                self.ds_each_update.append(output_storage)
            elif configuration["trigger"] == "change":
                self.ds_change_update.append(output_storage)
            else:
                print("Unknown trigger:", configuration["trigger"])

        # Setting the inputs
        # Corrently only group inputs are used
        all_inputs = self.config.get_input_params()
        if "sig_inputs" in all_inputs:
            if all_inputs["sig_inputs"]["type"] == "group":
                self.group_input = all_inputs["sig_inputs"]
            else:
                self.group_input = None
                print("Unknown input type:", all_inputs["type"])
        print("Inputs:", all_inputs)

    def start_sumo(self):
        """Starts the sumo"""
        try:
            traci.start(
                [self.sumo_bin, 
                "-c", 
                self.sumo_file,
                "--step-length", str(TIMER_PARAMS["time_step"]),
                "--start",
                "--quit-on-end"]
                )
        except Exception as e:
            print("Error starting sumo:", e)
            sys.exit(1)

    async def connect_nats(self):
        """Connects to the nats server"""
        self.nats = NATS()
        await self.nats.connect(self.nats_server)


    async def send_statuses_to_nats(self):
        """This function will handle all the reading from sumo as well as sending data into nats"""
        # the ones sent every update
        for data_source in self.ds_each_update:
            # Will return a dictionary type: {topic: message}
            messages = data_source.get_messages_current()
            for topic in messages:
                await self.nats.publish(topic, messages[topic])

        # the ones sent only when changed
        for data_source in self.ds_change_update:
            # Will return a dictionary type: {topic: message}
            messages = data_source.get_messages_changed()
            for topic in messages:
                await self.nats.publish(topic, messages[topic])

    
    def update_sumo(self):
        """This function will update the sumo simulation"""
        try:
            traci.simulationStep()
        except traci.exceptions.FatalTraCIError as e:
            print("Error in simulation step:", e)
            return False
        return True

    async def run(self):
        """Runs the system"""
        self.start_sumo()
        await self.connect_nats()
        # TODO: Callbacks for control messages to be added here
        # Loop for handling the simulation
        if self.group_input:
            group_control_channel = self.group_input["topic_prefix"] + ".*.*"
            async def sig_group_message_handler(msg):
                subject = msg.subject
                reply = msg.reply
                data = msg.data.decode()
                #print("Received a message on '{subject} {reply}': {data}".format(
                #    subject=subject, reply=reply, data=dat a))
                msg_dict = json.loads(data)
                set_sumo_traffic_light_state(subject, msg_dict)
            # As an inital state we set all the lights to red
            self.set_all_sumo_groups_to_red()
            # Sleep for five seconds to get all to red
            await asyncio.sleep(5)
            # And now we subscribe to the control messages
            await self.nats.subscribe(group_control_channel, cb=sig_group_message_handler)

        self.draw_radars()
        while traci.simulation.getMinExpectedNumber() > 0:
            if not self.update_sumo():
                break
            # This will handle all the data stream from sumo to nats
            await self.send_statuses_to_nats()

            # To sync with realtimer
            self.system_timer.tick()
            # Note, if Sumo is stopped by hand, this will try to catch up
            await asyncio.sleep(self.system_timer.get_next_time_step())

    def draw_radars(self):
        radar_polygons = self.config.get_radar_polygons()
        for rad_id, rad_coords in radar_polygons.items():
            self.draw_polygon(rad_id, rad_coords)

    def draw_polygon(self, polygon_name, coordinates, geo=True, color = (200,200,200), layer=0, line_width=0.1, fill=True):
        "Draws polygon to sumo for given coordinates"
        polygon = []
        coordinates.append(coordinates[0])
        for pair in coordinates:
            if geo:
                x, y = traci.simulation.convertGeo(pair[1], pair[0], fromGeo=True)
                polygon.append((x,y))
            else:
                polygon.append(tuple(pair))
        traci.polygon.add(polygon_name, polygon, color, layer=layer, lineWidth=line_width, fill=fill)

    def set_all_sumo_groups_to_red(self):
        "Initializes all traffic lights to red"
        sumo_lights = traci.trafficlight.getIDList()
        for light_id_sumo in sumo_lights:
            cur_state = traci.trafficlight.getRedYellowGreenState(light_id_sumo)
            all_Red = len(cur_state) * "r"
            traci.trafficlight.setRedYellowGreenState(light_id_sumo, all_Red)
        
    def set_sumo_traffic_light_state(self, channel, message):
        """Sets the traffic light state based on the message received from the nats server
            (This message is sent by the clockwork or other external controller)
        """
        controller_id = channel.split(".")[-2]
        light_id = int(channel.split(".")[-1])
        controller_id = "270_Tyyn_Vali" #Debug
        if 'green' in message:
            # Control message
            if message['green'] == True:
                sumo_group_state = "g"
            else:
                sumo_group_state = "r"
        else:
            # Status message contains no command for green
            # We induce the state from the substate
            if message['substate'] in GREEN_SUBSTATES:
                sumo_group_state = "g"
            else:
                sumo_group_state = "r"

        traci.trafficlight.setLinkState(controller_id, light_id, sumo_group_state)


async def main():
    # The command line params are set here
    command_line_params = read_command_line()
    config = GlobalConf(command_line_params=command_line_params, conf=command_line_params.conf)

    # After this all the configuration is in the "config"
    nats_server = config.get_nats_params()
    sumo_file = config.get_sumo_config()
    # Graphical UI for SUMO
    #if command_line_params.graph:
    if config.graph_mode():
        sumo_bin=SUMO_BIN_GRAPH
    else:
        sumo_bin=SUMO_BIN_NO_GRAPH

    # External controller used
    if command_line_params.external_controller:
        print("External controller enabled")
        external_controller = True
    else:
        external_controller = False


    # FIX ME 
    if command_line_params.use_group_status:
        group_control_channel_prefix = GROUP_CHANNEL_STATUS
    else:
        group_control_channel_prefix = GROUP_CHANNEL_CONTROL
        
    # Start the sumo
    try:
        traci.start(
            [sumo_bin, 
             "-c", 
             sumo_file,
             "--step-length", str(TIMER_PARAMS["time_step"]),
             "--start",
             "--quit-on-end"]
             )
    except Exception as e:
        print("Error starting sumo:", e)
        sys.exit(1)

    # Note: might be set by params in the future
    system_timer = Timer(TIMER_PARAMS)

    nats = NATS()
    await nats.connect(nats_server)

    # This callback handles the command messages from the NATS server (clockworrk or reality)
    # The sumo model should follow these commands
    async def sig_group_message_handler(msg):
        subject = msg.subject
        reply = msg.reply
        data = msg.data.decode()
        #print("Received a message on '{subject} {reply}': {data}".format(
        #    subject=subject, reply=reply, data=dat a))
        msg_dict = json.loads(data)
        set_sumo_traffic_light_state(subject, msg_dict)
    
    # All red and expecting messages
    if external_controller:
        print("Subscribing to:", group_control_channel_prefix)
        sub = await nats.subscribe(group_control_channel_prefix, cb=sig_group_message_handler)
        set_all_sumo_groups_to_red()


    det_storage = DetStorage()
    DetStorage.test()
    while traci.simulation.getMinExpectedNumber() > 0:
        try:
            traci.simulationStep()
        except traci.exceptions.FatalTraCIError as e:
            print("Error in simulation step:", e)
            break
        
        # This is changes the yelding operation of the vehicles
        # That is, they will enter "congested" junctions as well
        # Could the be done for all vehicles without a need to do it at every update?
        for vehicleId in traci.vehicle.getIDList():
            traci.vehicle.setSpeedMode(vehicleId,55) # disable right of way check, vehicles can enter the junction, despite queue end


        system_timer.tick()
        # Note, if Sumo is stopped by hand, this will try to catch up
        await asyncio.sleep(system_timer.get_next_time_step())
        if config.send_det_statuses():
            #det_statuses = get_detector_statuses()
            det_statuses = det_storage.read_det_values_from_sumo()
            for det_status in det_statuses:
                # We only send the status if it has changed
                if det_storage.add_det_value(det_status["id"], det_status["loop_on"]):
                    det_id = DET_CHANNEL_PREFIX + "." + det_status["id"]
                    det_status["id"] = det_id
                    det_status_json = json.dumps(det_status)
                    # Debug: we remove all the publishes REMOVE
                    await nats.publish(det_id, det_status_json.encode())
        #det_statuses_json = json.dumps(det_statuses)
        #await nats.publish(DET_CHANNEL_PREFIX, det_statuses_json.encode())
        light_statuses = get_traffic_light_statatuses()
        for light_status in light_statuses:
            light_id = GROUP_CHANNEL_PREFIX + "." +  light_status["id"].rsplit(".")[-1]
            light_status["id"] = light_id
            #print(light_status)
            light_status_json = json.dumps(light_status)
            # Debug: we remove all the publishes REMOVE
            await nats.publish(light_id, light_status_json.encode())
        #print(system_timer.aggregate_time_drift)

def set_sumo_traffic_light_state(channel, message):
    """Sets the traffic light state based on the message received from the nats server
        (This message is sent by the clockwork or other external controller)
    """
    #print("DEBUG:", channel, message)
    controller_id = channel.split(".")[-2]
    light_id = int(channel.split(".")[-1])
    controller_id = "270_Tyyn_Vali" #Debug
    if 'green' in message:
        # Control message
        if message['green'] == True:
            sumo_group_state = "g"
        else:
            sumo_group_state = "r"
    else:
        # Status message contains no command for green
        # We induce the state from the substate
        if message['substate'] in GREEN_SUBSTATES:
            sumo_group_state = "g"
        else:
            sumo_group_state = "r"

    traci.trafficlight.setLinkState(controller_id, light_id, sumo_group_state)

def set_all_sumo_groups_to_red():
    "Initializes all traffic lights to red"
    sumo_lights = traci.trafficlight.getIDList()
    for light_id_sumo in sumo_lights:
        cur_state = traci.trafficlight.getRedYellowGreenState(light_id_sumo)
        all_Red = len(cur_state) * "g" # DEBUG FIX ME
        traci.trafficlight.setRedYellowGreenState(light_id_sumo, all_Red)

def get_detector_statuses():
    "Returns dict of detector statuses"
    sumo_loops = traci.inductionloop.getIDList()
    det_statuses = []
     
    for det_id_sumo in sumo_loops:
        det_status = {}
        det_status["id"] = det_id_sumo
        #current_time = datetime.now()
        current_time = str(datetime.now()).replace(" ", "T") + "Z"
        det_status["tstamp"] = str(current_time)
        
        vehnum = traci.inductionloop.getLastStepVehicleNumber(det_id_sumo)
        occup = traci.inductionloop.getLastStepOccupancy(det_id_sumo)

        if (vehnum > 0) or (occup > 0):   # DBIK 10.22  or (occup > 0):
            loop_on = True
        else:
            loop_on = False
        det_status["loop_on"] = loop_on
        det_statuses.append(det_status)
    return det_statuses

def get_traffic_light_statatuses():
    "Returns dict of traffic light statuses"
    sumo_lights = traci.trafficlight.getIDList()
    light_statuses = []
    current_time = datetime.now()

    for light_id_sumo in sumo_lights:
        statuses = traci.trafficlight.getRedYellowGreenState(light_id_sumo)
        id = 0
        for status in statuses:
            light_status = {}
            light_status["id"] = light_id_sumo + "." + str(id)
            light_status["tstamp"] = str(current_time)
            light_status["substate"] = status
            id += 1
            light_statuses.append(light_status)
    return light_statuses




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



    parser.add_argument('--sumo-conf',
                                help='Sumo model to execute '
                                    '(default: default.conf)',
                                required=True)


    parser.add_argument('--print-status',
                                help='If set, prints status info in every update',
                                action='store_true',
                                required=False)

    parser.add_argument('--graph',
                                help='If set, opens graphical version of sumo',
                                action='store_true',
                                required=False)

    # For external traffic controller
    parser.add_argument('--external-controller',
                                help='If set, enables external controller',
                                action='store_true',
                                required=False)
    
    parser.add_argument('--nats-server',
                                help='Nats server address ',
                                required=False)
    parser.add_argument('--nats-port',
                                help='Nats server port ',
                                required=False)
    
    parser.add_argument('--use-group-status',
                                help='If set, we update the groups in the simulation with status messages'
                                    'If not set we use control messages',
                                action='store_true',
                                required=False)

    args = parser.parse_args()

    return args


if __name__ == "__main__":
    interface = SumoNatsInterface()
    asyncio.run(interface.run())
    
    #args = read_command_line()
    #print(args)
    #exit()
    print("Running Sumo")
    #asyncio.run(main())