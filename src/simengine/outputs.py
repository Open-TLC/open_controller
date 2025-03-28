# -*- coding: utf-8 -*-
""" Output storage and handling
"""

import os
import sys
import json
from datetime import datetime
from shapely.geometry import Polygon, Point
from vehicle import Vehicle

if 'SUMO_HOME' in os.environ:
    SUMO_TOOLS = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(SUMO_TOOLS)
    import traci
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")


CLENUP_TIME_LIMIT = 0.5 # seconds
RSU_DATA_PREFIX = "v2x.rsu" #later from conf


class Radar:
    "This class is for handling the virtual radars"
    def __init__(self, aoi, lane_map=None, vehicle_types=None):
        # aoi = area of interest
        poly_coords = []
        if aoi:
            for point in aoi:
                poly_coords.append(tuple(point))
            self.aoi = Polygon(poly_coords)
        else:
            self.aoi = None
        
        self.lane_map = lane_map
        self.vehicle_types = vehicle_types
        self.vehicles = {}
        self.id_counter = 0

    def get_new_id(self):
        "Returns a new unique id for the vehicle"
        prev_id = self.id_counter
        self.id_counter += 1
        if self.id_counter > 255:
            self.id_counter = 0
        return prev_id

    def add_vehicle(self, new_veh):
        "Adds the vehicel to the radar if it is in the area of interest"
        # filter out the vehicles that are not of pre-defined type
        if self.vehicle_types:
            if not new_veh['sumo_type'] in self.vehicle_types:
                return
        
        # Filter out all the vehs outside aoi, if it is defined
        if self.aoi:
            if not self.aoi.contains(new_veh['sumo_loc']):
                return
        
        # If no aoi or veh within it, we add the vehicle
        veh = dict(new_veh)
        if not veh['sumo_id'] in self.vehicles:
            # We need to generate an id for the vehicle
            veh['id'] = self.get_new_id()
        else:
            veh['id'] = self.vehicles[veh['sumo_id']]['id']
            

        # We update the values    
        vehicle_id = veh['sumo_id']
        veh['lat'] = veh['sumo_loc'].x
        veh['lon'] = veh['sumo_loc'].y
        

        speed = traci.vehicle.getSpeed(vehicle_id)
        angle = traci.vehicle.getAngle(vehicle_id)
        veh['speed'] = speed
        veh['acceleration'] = traci.vehicle.getAcceleration(vehicle_id)
        veh['sumo_angle'] = angle
        veh['len'] = traci.vehicle.getLength(vehicle_id)
        veh['lane'] = self.get_veh_lane(vehicle_id)
        veh['cyc_ago'] = 0

        sumo_class = traci.vehicle.getTypeID(vehicle_id)           
        # FIXME: These should be configurable
        veh['sumo_class'] =  sumo_class
        if sumo_class == 'car_type':
            veh['class'] = 4
        elif sumo_class == 'truck_type':
            veh['class'] = 7
        else:
            veh['class'] = sumo_class

        
        veh['quality'] = 100        
        veh['lastupdate'] = datetime.now()
        # Finally we add/replace the vehicle data
        self.vehicles[veh['sumo_id']] = veh


    def get_veh_lane(self, vehicle_id):
        "Returns the lane of the vehicle"
        if not self.lane_map:
            sumo_lane = traci.vehicle.getLaneIndex(vehicle_id)
            return sumo_lane
        
        #Mapping is defined
        sumo_lane_id = traci.vehicle.getLaneID(vehicle_id)
        if sumo_lane_id in self.lane_map:
            return self.lane_map[sumo_lane_id]
        else:
            #print("Lane not found in the lane map:", sumo_lane_id)            
            return -1 # TODO: Should be handled better, maybe omit these vehicles?


    def remove_old_data(self):
        "Removes the vehicles that have not been updated for a while"
        # We need to check the age of the data
        for veh_id in list(self.vehicles.keys()):
            veh = self.vehicles[veh_id]
            now = datetime.now()
            lats_update = veh['lastupdate']
            time_since_update = (now - lats_update).total_seconds()
            if time_since_update > CLENUP_TIME_LIMIT:
                del self.vehicles[veh_id]


    def get_radar_data(self):
        """Returns 'sumo radar' data to twinobject for updating veh tracking
            This data should be the same format as in the live radar output
        """
        tstamp = round(datetime.now().timestamp() * 1000)
        data = {}
        data['source'] = 'sumo'
        data['status'] = 'OK'
        data['tstamp'] = tstamp    
        data['nobjects'] = len(self.vehicles)    
        data['objects'] = []
        for veh in self.vehicles.values():
            # We copy the dict to avoid modifying the original
            # Note: this could be improved, maybe we should use a class
            out_vehicle = dict(veh)
            del out_vehicle['sumo_loc'] # Wont serialize
            del out_vehicle['lastupdate'] # Wont serialize
            data['objects'].append(out_vehicle)
        return data

    def get_all_vehicle_data(self):
        """Returns all the vehicle data for vehicles within the radar"""
        vehlist = []
        for veh in self.vehicles.values():
            out_vehicle = dict(veh)
            vehlist.append(out_vehicle)
        return vehlist




class DetStorage:
    "This is a class for storing the detector states and indicating any change"
    def __init__(self, conf):
        # this will contain the dictionary of all the detector messages
        self.statuses = {}
        self.conf = conf
        self.topic_prefix = conf['topic_prefix']

    def add_det_value(self, det_id, loop_on):
        "Adds a detector status to the dictionary returns True if the status has changed"
        if det_id not in self.statuses:
            self.statuses[det_id] = loop_on
            return True
        elif loop_on != self.statuses[det_id]:
            self.statuses[det_id] = loop_on
            return True
        return False

    def read_det_values_from_sumo(self):
        "Returns dict of detector statuses"
        sumo_loops = traci.inductionloop.getIDList()
        det_statuses = {}
        
        for det_id_sumo in sumo_loops:
            det_status = {}

            current_time = datetime.now().isoformat()
            det_status["tstamp"] = str(current_time)
            
            vehnum = traci.inductionloop.getLastStepVehicleNumber(det_id_sumo)
            occup = traci.inductionloop.getLastStepOccupancy(det_id_sumo)

            if (vehnum > 0) or (occup > 0):   # DBIK 10.22  or (occup > 0):
                loop_on = True
            else:
                loop_on = False
            det_status["loop_on"] = loop_on
            det_statuses[det_id_sumo] = det_status
        return det_statuses

    def get_messages_current(self):
        """Returns a dict with data to be send to NATS"""
        messages = {}
        from_sumo = self.read_det_values_from_sumo()
        for det_id in from_sumo:
            det_status = {}
            det_status["id"] = self.topic_prefix + '.' +  det_id
            det_status["loop_on"] = from_sumo[det_id]["loop_on"]
            det_status["tstamp"] = str(datetime.now().isoformat())
            det_status_json = json.dumps(det_status)
            messages[self.topic_prefix + "." + det_id] = det_status_json.encode()
        return messages

    def get_messages_changed(self):
        """Returns a dict with data to be send to NATS, but only for the ones changed"""
        messages = {}
        from_sumo = self.read_det_values_from_sumo()
        for det_id in from_sumo:
            if self.add_det_value(det_id, from_sumo[det_id]["loop_on"]):
                det_status = {}
                det_status["id"] = self.topic_prefix + '.' + det_id
                det_status["loop_on"] = from_sumo[det_id]["loop_on"]
                det_status["tstamp"] = str(datetime.now().isoformat())
                det_status_json = json.dumps(det_status)
                messages[self.topic_prefix + "." + det_id] = det_status_json.encode()
        return messages


    def test():
        print("Test")

class GroupStorage:
    """This is a class for string the groups statuses"""
    def __init__(self, conf):
        self.statuses = {}
        self.conf = conf
        self.topic_prefix = conf['topic_prefix']

    def read_group_statuses_from_sumo(self):
        "Returns dict of traffic light statuses"
        sumo_lights = traci.trafficlight.getIDList()
        light_statuses = {}
        current_time = datetime.now().isoformat()

        for light_id_sumo in sumo_lights:
            statuses = traci.trafficlight.getRedYellowGreenState(light_id_sumo)
            id = 0
            for status in statuses:
                light_status = {}
                # This is temproray fix for replicating the reality
                controller_id = light_id_sumo.split("_")[0]
                light_id = controller_id + "." + str(id)
                light_status["id"] = self.topic_prefix + "." + light_id

                light_status["tstamp"] = str(current_time)
                light_status["substate"] = status
                id += 1
                light_statuses[light_id] = light_status
        return light_statuses
    
    def get_messages_current(self):
        """Returns a dict (keys are channels, values are json-strings) with data to be send to NATS"""
        messages = {}
        from_sumo = self.read_group_statuses_from_sumo()
        for group_id in from_sumo:
            light_status_json = json.dumps(from_sumo[group_id])
            messages[self.topic_prefix + "." + group_id] = light_status_json.encode()
        return messages

    def add_group_value(self, group_id, substate):
        "Adds a group status to the dictionary returns True if the status has changed"
        if group_id not in self.statuses:
            self.statuses[group_id] = substate
            return True
        elif substate != self.statuses[group_id]:
            self.statuses[group_id] = substate
            return True
        return False

    def get_messages_changed(self):
        """Returns a dict (keys are channels, values are json-strings) 
            with data to be send to NATS, but only for the ones changed"""
        messages = {}
        from_sumo = self.read_group_statuses_from_sumo()
        for group_id, group_vals in from_sumo.items():
            if self.add_group_value(group_id, group_vals["substate"]):
                light_status_json = json.dumps(group_vals)
                messages[self.topic_prefix + "." + group_id] = light_status_json.encode()
        return messages

class RadarStorage:
    """
        This is a class for storing the radar detections we use Radar objects for storing the data
        This storage thus covers all the radars defined in the configuration as outputs and 
        functions for receiving the data from the SUMO and updating the radar objects
    """
    def __init__(self, conf):
        self.statuses = {}
        self.conf = conf

        for rad_id, rad_conf in self.conf['radars'].items():
            # Lane map, if defined
            if 'lane_map' in rad_conf:
                lane_map = rad_conf['lane_map']
            else:
                lane_map = None
            
            # Area of interest, if defined
            if 'area_of_interest' in rad_conf:
                aoi = rad_conf['area_of_interest']
            else:
                aoi = [] # same as empty list, if it is set in the conf
            
            # Vehicle type list, if defined
            if 'vehicle_types' in rad_conf:
                vehicle_types = rad_conf['vehicle_types']
            else:
                vehicle_types = None

            self.conf['radars'][rad_id]['radar_object'] = Radar(aoi, lane_map=lane_map, vehicle_types=vehicle_types)
        
    def get_messages_current(self):
        """Returns a dict (keys are channels, values are json-strings) with data to be send to NATS"""
        self.update_radars()
        messages = {}
        for radar_conf in self.conf['radars'].values():
            radar_data = radar_conf['radar_object'].get_radar_data()
            radar_status_json = json.dumps(radar_data)
            messages[radar_conf["topic"]] = radar_status_json.encode()
        return messages
    
    def update_radars(self):
        """We read the objects from the SUMO and update them to the radar objects"""
        for radar_conf in self.conf['radars'].values():
                radar_conf['radar_object'].remove_old_data()
        
        veh_id_list = traci.vehicle.getIDList()
        for vehicle_id in veh_id_list:
            new_vehicle = {}
            new_vehicle['sumo_id'] = vehicle_id
            # We need to calculate the location in order for the radar to determine
            # whether the vehicle is within radar beam (in the area of interest)
            pos_x, pos_y = traci.vehicle.getPosition(vehicle_id)
            lon, lat = traci.simulation.convertGeo(pos_x, pos_y)
            new_vehicle['sumo_loc'] = Point(lat, lon)
            # We also need the vehicle type, in case we want to filter the vehicles
            # based on the type
            new_vehicle['sumo_type'] = traci.vehicle.getTypeID(vehicle_id) 
            for radar_conf in self.conf['radars'].values():
                radar_conf['radar_object'].add_vehicle(new_vehicle)


    def get_vehicle_data_from_radars(self):
        "Returns the vehicle data from the radars"
        vehicle_data = []
        for radar_conf in self.conf['radars'].values():
            vehicle_data += radar_conf['radar_object'].get_all_vehicle_data()
        return vehicle_data

# This is for storing the vehicles inside a given RSU

class VehStorage():
    "This is a class for storing the vehicles with V2X capabilities"

    # In essence this unit contains a "radar" that is functionality for accessing 
    # The vehicles in given area and of given type
    # in addition to this, we create a copy of each vehicle "digital twin" that is used
    # For 1) handling the messages from individual vehicles and 2) for coping with signing and such
    def __init__(self, conf):
        # map rsus as radars
        # RSU setup is similar to radar setup, but with some additional parameters
        # We add the "radar" setup in order to use the radar storage
        if "rsus" in conf:
            # deep copy the parameters
            conf["radars"] = conf["rsus"].copy()

        self.radar_storage = RadarStorage(conf)
        self.vehs = {}    
        if "channel_prefix" in conf:
            self.channel_prefix = conf["channel_prefix"]
        else:
            self.channel_prefix = RSU_DATA_PREFIX

    
    
    def get_messages_current(self):
        vehdata= self.radar_storage.get_vehicle_data_from_radars()
        #print(vehdata)
        # Note, this updates, we have to add it when we change this
        self.radar_storage.update_radars()
        for vehdict in vehdata:
            veh_id = vehdict['sumo_id'] # Note, this should be prefix FIXME
            if veh_id not in self.vehs:
                self.vehs[veh_id] = Vehicle(veh_id) # New vehicle greated, if not available
            self.vehs[veh_id].add_data(vehdict)

        ret_messages = {}
        for veh_id, veh in self.vehs.items():
            # We get the message to send
            message = veh.get_message_to_send()
            if message:
                message_json = json.dumps(message)
                ret_messages[RSU_DATA_PREFIX + '.' + veh_id] = message_json.encode()

        #print (ret_messages)
        #ret_messages2 = self.radar_storage.get_messages_current()
        #ret_messages={
        #    'v2x.vehicles.1': "test".encode(),
        #    'v2x.vehicles.2': "test2".encode(),
        #}
        return ret_messages
    

