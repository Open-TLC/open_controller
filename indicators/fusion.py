"""
    This unit contains functionality for handling calculation ofoutputs based
    on multible inputps. In essence we formulate a "Field Of View" and map 
    relevant inputs into it. All data manipualtaion and calculation needed 
    for outputs will be handled here
"""
import asyncio
import datetime
import json

class Lane:
    """Lane indicators contained"""
    def __init__(self, params):
        self.in_dets = {} # detectors for incoming traffic
        self.out_dets = {} # detectors for outgoing traffic
        self.input_radars = {}
        self.input_radars_params = params.get('radar_lanes', {})
        self.in_dets_params = params.get('in_dets', {})
        self.out_dets_params = params.get('out_dets', {})

    def assign_radars(self, radars):
        """Assigns a radar to the lane"""
        for radar_name, radar_params in self.input_radars_params.items():
            if radar_params['stream'] in radars:
                lane = radar_params['lane']
                radar = radars[radar_params['stream']]
                #self.input_radars[radar_name] = radars[radar_params['stream']]
                self.input_radars[radar_name] = LaneRadar(lane, radar)

        #print(f"assigned radars: {self.input_radars}")

    def assign_detectors(self, detectors):
        """Assigns in and out detectors to the lane"""
        # In dets
        for det_name, det_params in self.in_dets_params.items():
            if det_params['name'] in detectors:
                self.in_dets[det_name] = detectors[det_params['name']]

        # Out dets
        for det_name, det_params in self.out_dets_params.items():
            if det_params['name'] in detectors:
                self.out_dets[det_name] = detectors[det_params['name']]

    # Note: currently doesn't handle multiple radars
    def get_approaching_objects(self):
        """Returns the number of approaching v"""
        approaching_objs = []
        for radar in self.input_radars.values():
            approaching_objs.extend(radar.get_approaching_objects())
        return approaching_objs

# This is basically only a container for the lane and radar pair
class LaneRadar:
    """Container for lane and radar pair"""

    def __init__(self, lane, radar):
        self.lane = lane
        self.radar = radar # object

    def __str__(self):
        return f"lane: {self.lane}, radar: {self.radar}"
    
    def get_approaching_objects(self):
        """Returns the number of approaching vehicles in the lane dedicated to this object"""
        # Old simle implementation
        objects = self.radar.get_object_list()
        objects_in_lane = []
        for obj in objects:
            if str(obj['lane']) == self.lane:
                objects_in_lane.append(obj)
        return objects_in_lane



class FieldOfView:
    """
        A class for defining field of view, this is set of inputs that are 
        relevant for the calculation of output values. Typically this is an
        approach for the traffic in a certain area."""
    
    def __init__(self, name, params):
        self.name = name
        self.params = params
        if params.get('trigger', False) == 'time':
            self.trigger_time = params.get('trigger_time', None)
        self.nats_output_subject = params.get('nats_output_subject', None)

        # We add the lanes, note that input streams are not added here
        # They are added after all the radar/detector objects are created
        # with the assign_radars function
        self.lanes = []
        lane_params = params.get('lanes', [])
        for lane_param in lane_params:
            lane = Lane(lane_param)
            self.lanes.append(lane)
    
    def assign_radars(self, radars):
        """Assigns radars to the field of view"""
        # Note: lane will make sure only the correct ones are assigned
        for lane in self.lanes:
            lane.assign_radars(radars)

    def assign_detectors(self, detectors):
        """Assigns detectors to the field of view"""
        # Note: lane will make sure onlu the correct ones are assigned
        for lane in self.lanes:
            lane.assign_detectors(detectors)

    def get_approaching_objects(self):
        """Returns the number of approaching vehicles"""
        approaching_objs = []
        for lane in self.lanes:
            approaching_objs.extend(lane.get_approaching_objects())
        return approaching_objs


    # Async function for sending the data out
    async def send_queues(self, nats):
        """Send the queue lengths to the nats"""
        while True:
            await asyncio.sleep(self.trigger_time)
            queue_lengths = self.get_approaching_objects()
            data = {}
            data['radar_id'] = self.name
            data['queue_lengths'] = queue_lengths
            data['tstamp'] = datetime.datetime.now().timestamp() * 1000
            if self.nats_output_subject:
                await nats.publish(self.nats_output_subject, json.dumps(data).encode())
                print(f"Sent queue data from {self.name}: {queue_lengths}")


