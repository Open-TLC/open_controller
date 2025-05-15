"""The radar module providing radars to be used by the SensorTwin"""

import datetime
import json
import asyncio
from geopy import distance as geopy_distance
from shapely.geometry import Polygon, Point

# Note: should be configureable
DEFAULT_CLEANUP_INTERVAL = 10 # seconds
DEFAULT_OLD_DATA_TRESHOLD = 60 # seconds 
DEFAULT_SEND_QUEUES_INTERVAL = 1 # seconds


class Radar:
    """The radar class"""

    def __init__(self, radar_id, radar_params):
        self.radar_id = radar_id
        self.radar_params = radar_params
        if radar_params['connection'] == 'nats':
            if 'nats_subject' in radar_params:
                self.nats_subject = radar_params['nats_subject']
                self.nats = True
                # From params in the future
                qs = self.nats_subject.rsplit('.')[0:-2]
                qs = '.'.join(qs) + '.queues.json'
                self.queue_subject = qs
            else:
                self.nats = False
                print(f"Radar {radar_id} is missing nats_subject".format(radar_id))
        else:
            self.nats = False
        
        # This is needed for detemining if the radar covers the area whrere the V2X is
        # This is used for teputation caliculation
        if 'aoi' in radar_params:
            self.aoi = Polygon(radar_params['aoi'])
        else:
            self.aoi = None

        self.data = []
        

    def __str__(self):
        return f"Radar id: {self.radar_id}, type: {self.radar_type}, params: {self.radar_params}"


    # Basic data access functions
    def add_data(self, data):
        """Adds data to the radar"""
        self.data.append(data)
       
    def remove_old_data(self, treshold=DEFAULT_OLD_DATA_TRESHOLD):
        "Removes all data with sent timestamp older than treshold"
        now = datetime.datetime.now()
        for data in self.data:
            if 'data_sent' in data:
                data_sent = data['data_received']
                diff = now - data_sent
                if diff.total_seconds() > treshold:
                    self.data.remove(data)
 
    def get_last_data(self):
        """Returns the last data item"""
        if len(self.data) == 0:
            return None
        # If there is an empty dataset, we should return the one before that
        # This fixes radar error, should be fixed elswhere and this to be removed
        if len(self.data[-1]['objects']) == 0:
            if len(self.data) > 1:
                return self.data[-2]
        return self.data[-1]

    def get_object_list(self, measurements = 1):
        """Returns the list of objects"""
        last_data = self.get_last_data()
        if len(self.data) <= 0:
            return []
        if measurements == 1:
            return last_data['objects']
        else:
            return self.get_object_list_for_n_measurements(measurements)

    def get_object_list_for_n_measurements(self, number_of_measurements):
        """
            Returns the list of objects for the last n measurements
            This should filter out totally empty messages
        """
        past_objects = {}
        data_available = len(self.data)
        if data_available >= number_of_measurements:
            n = number_of_measurements
        else:
            n = data_available
        last_data = self.data[:-n]
        for data in last_data:
            for obj in data['objects']:
                id = obj['id']
                past_objects[id] = obj
            
        ret_list = []
        for obj in past_objects.values():
            ret_list.append(obj)
        return ret_list



    def get_nats_sub_params(self):
        """
            Returns the nats subscription parameters 
            (dict of subject and callback function)
            returns none if nats is not used (or subject not defined)"""
        if not self.nats:
            return None
        params = {}
        params['subject'] = self.nats_subject
        params['callback'] = self.nats_callback
        return params


     
    def get_queue_lengths_by_lane(self):
        """Returns the queue lengths by lane"""
        last_data = self.get_last_data()
        if not last_data:
            return {} # No data
        
        queue_lengths = {}
        objects = last_data['objects']
        for obj in objects:
            lane = obj['lane']
            if lane not in queue_lengths:
                queue_lengths[lane] = 0
            queue_lengths[lane] += 1
                
        return queue_lengths

#
#    Functions for hangling the V2X to radar comparisions
#

    # Function for finding the closest object in the last radar data
    # We use geopy functions to for finding the closest ones
    # Note: this 1) only wirks for latest data, 2) only for one radar
    # Expansieions should be done in the future
    # Wa give trashold as a parameters, and return None if the object is not found
    # or it is too far away
    def get_closest_object(self, point, treshold=0.5):
        """Returns the closest object to the given point
        point: point (lat, lon) in degrees
        treshold: distance treshold (in meters)
        returns: closest object (dictionary) or None if not found
        """
        last_data = self.get_last_data()
        if not last_data:
            return None
        
        objects = last_data['objects']
        if len(objects) == 0:
            return None
        closest_object = None
        closest_distance = None
        for obj in objects:
            obj_point = (obj['lat'], obj['lon'])
            dist = geopy_distance.distance(point, obj_point).m
            if closest_distance is None or dist < closest_distance:
                closest_distance = dist
                closest_object = obj
        if closest_distance is None or closest_distance > treshold:
            return None
        # Add the distance to the object
        closest_object['distance_to_v2x'] = closest_distance
        return closest_object

    def is_point_in_aoi(self, latlon):
        """Checks if the latlon is in the area of interest (aoi)"""
        # No area defined -> wa assume the whole world is the aoi
        if self.aoi is None:
            return True
        # Check if the latlon is in the aoi, we use the geopy library for this
        p = Point(latlon[0], latlon[1])
        if self.aoi.contains(p):
            return True
        else:
            return False


#    
# ASYNC functions
#
    async def cleanup_old_data(self):
        """Removes old data, this should be a separate task running at alla times"""
        while True:
            await asyncio.sleep(DEFAULT_CLEANUP_INTERVAL)
            #print(self.radar_id, ":", self.get_queue_lengths_by_lane())
            self.remove_old_data()

    async def nats_callback(self, msg):
        """The callback function for the nats and is assigned to the subscription"""
        subject = msg.subject
        reply = msg.reply
        data = msg.data.decode()
        #print(f"Received a message on '{subject} {reply}': {data}")
        data_dict = json.loads(data)
        if 'tstamp' in data_dict:
            tstamp = data_dict['tstamp']
            tstamp_in_datetime = datetime.datetime.fromtimestamp(tstamp/1000)
            tstamp_now = datetime.datetime.now()
            data_dict['data_sent'] = tstamp_in_datetime
            data_dict['data_received'] = tstamp_now
        self.add_data(data_dict)

    async def send_queues(self, nats):
        """Send the queue lengths to the nats"""
        while True:
            await asyncio.sleep(DEFAULT_SEND_QUEUES_INTERVAL)
            queue_lengths = self.get_queue_lengths_by_lane()
            data = {}
            data['radar_id'] = self.radar_id
            data['queue_lengths'] = queue_lengths
            data['tstamp'] = datetime.datetime.now().timestamp() * 1000
            await nats.publish(self.queue_subject, json.dumps(data).encode())
            #print(f"Sent queue data from {self.radar_id}: {queue_lengths}")