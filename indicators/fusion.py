"""
    This unit contains functionality for handling calculation ofoutputs based
    on multible inputps. In essence we formulate a "Field Of View" and map 
    relevant inputs into it. All data manipualtaion and calculation needed 
    for outputs will be handled here
"""
import asyncio
import datetime
import json
import uuid

# Maybe configurable in the future, done for demo
VECLASS_FROM_RADAR_TO_SUMO = {
    2: "car_type",
    4: "truck_type"
}

class Lane:
    """Lane indicators contained"""
    def __init__(self, params):
        self.name = params.get('name', "No name")
        self.in_dets = {} # detectors for incoming traffic
        self.out_dets = {} # detectors for outgoing traffic
        self.input_radars = {}
        self.input_radars_params = params.get('radar_lanes', {})
        self.in_dets_params = params.get('in_dets', {})
        self.out_dets_params = params.get('out_dets', {})
        # These will be updated based on detector values
        self.indet_count = 0
        self.outdet_count = 0
        self.vehcount_offset = 0 # For correctiong the drifting of the detcunt

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
            if not det_params:
                print("Warning: Det params missing for: ", det_name)
                continue
            if det_params['name'] in detectors:
                self.out_dets[det_name] = detectors[det_params['name']]
 

    # Note: currently doesn't handle multiple radars
    def get_approaching_objects(self):
        """Returns the number of approaching v"""
        approaching_objs = []
        for radar in self.input_radars.values():
            approaching_objs.extend(radar.get_approaching_objects())
        return approaching_objs

    def get_detected_objects_e3(self):
        """Returns the number of approaching v"""
        detected_objects = []
        for radar in self.input_radars.values():
            detected_objects += radar.get_approaching_objects()
        return detected_objects

    def get_detector_based_vehcount(self):
        """Returns the vehicle count based on detectors"""
        in_count = 0
        out_count = 0
        for det in self.in_dets.values():
            in_count += det.get_vehicle_count()
        for det in self.out_dets.values():
            out_count += det.get_vehicle_count()
        return in_count - out_count + self.vehcount_offset

    def reset_detector_based_vehcount(self):
        """Resets the vehcount to zero"""
        self.vehcount_offset = -1 * self.get_detector_based_vehcount()


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
        self.view_type = params.get('type', "")
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
        self.group_name = params.get('group', None)
        self.group = None

    #
    # Assigning functions (maps the input streams to the view)
    # 

    def assign_radars(self, radars):
        """Assigns radars to the field of view"""
        # Note: lane will make sure only the correct ones are assigned
        for lane in self.lanes:
            lane.assign_radars(radars)

    def assign_detectors(self, detectors):
        """Assigns detectors to the field of view"""
        # Note: lane will make sure only the correct ones are assigned
        for lane in self.lanes:
            lane.assign_detectors(detectors)

    def assign_groups(self, groups):
        """Assigns groups to the field of view"""
        if not self.group_name:
            print("Warning: No group assigned to field of view: ", self.name)
            return
        for group in groups.values():
            if group.group_id == self.group_name:
                self.group = group
                self.group.add_reset_counter_function(self.reset_lane_detector_vehcounters)

        
    #
    # Calculating outputs
    #

    def get_detector_based_vehcount(self):
        """Returns the vehicle count based on detectors"""
        vehcount = 0
        for lane in self.lanes:
            vehcount += lane.get_detector_based_vehcount()
        return vehcount

    def get_approaching_objects(self):
        """Returns the number of approaching vehicles"""
        approaching_objs = []
        for lane in self.lanes:
            new_lane = {}
            new_lane['lane'] = lane.name
            new_lane['approaching'] = lane.get_detector_based_vehcount()
            approaching_objs.append(new_lane)
        return approaching_objs

    def get_objects_in_all_lanes(self):
        """Returns the number of approaching vehicles"""
        detected_objects = []
        for lane in self.lanes:
            detected_objects += lane.get_detected_objects_e3()
        return detected_objects

    def reset_lane_detector_vehcounters(self):
        """Resets the vehcounts to zero for all the lanes"""
        for lane in self.lanes:
            lane.reset_detector_based_vehcount()

    # Async function for sending the data out
    async def send_nats_messages(self, nats):
        """Send the queue lengths to the nats"""
        while True:
            await asyncio.sleep(self.trigger_time)
            if self.view_type == "grp_view":
                out_data = self.get_linewise_ouptut()
            elif self.view_type == "e3":
                out_data = self.get_e3_area_output()
            else:
                print("Type: {} not supported".format(self.view_type))
                continue
            if self.nats_output_subject:
                await nats.publish(self.nats_output_subject, json.dumps(out_data).encode())
                #print(f"Sent queue data from {self.name}: {queue_lengths}")


    def get_linewise_ouptut(self):
        """Returns a dictionary for the queue output type"""
        queue_lengths = self.get_approaching_objects()
        data = {}
        if self.group:
            data['group_status'] = self.group.substate
        else:
            data['group_status'] = "NO group defined"
        data['radar_id'] = self.name
        data['queue_lengths'] = queue_lengths
        data['tstamp'] = datetime.datetime.now().timestamp() * 1000
        return data
    
    def get_e3_area_output(self):
        """Returns the output for the E3 area"""
        detected_objects = self.get_objects_in_all_lanes()
        det_obj_dict = {}
        for obj in detected_objects:
            new_obj = {}
            obj_id = obj.get('id', uuid.uuid4())
            new_obj['speed'] = obj.get('speed', None)
            
            vehclass_radar = obj.get('class', None)
            vehclass_sumo = VECLASS_FROM_RADAR_TO_SUMO.get(vehclass_radar, None)
            if not vehclass_sumo:
                print(f"Warning: Vehicle class not found for radar class: {vehclass_radar}")
            new_obj['vtype'] = vehclass_sumo
            new_obj['sumo_id'] = obj.get('sumo_id', None)
            # Note: we only add the types of objects we know, this is a temporary solution
            # Sumo simengine does not map types and lanes correctly (yet)
            if vehclass_sumo:
                det_obj_dict[obj_id] = new_obj
        data = {}
        data['count'] = len(det_obj_dict)
        det_vehcount = self.get_detector_based_vehcount()
        if det_vehcount < 0:
            self.reset_lane_detector_vehcounters()
            det_vehcount = 0
        data['det_vehcount'] = det_vehcount
        data['group_substate'] = self.group.substate
        data['view_name'] = self.name
        data['objects'] = det_obj_dict
        data['tstamp'] = datetime.datetime.now().timestamp() * 1000
        return data