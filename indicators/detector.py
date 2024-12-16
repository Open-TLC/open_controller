"This Unit contains handlers for the detector inputs and outputs."

import datetime
import json
import asyncio

# Note: should be configureable
DEFAULT_CLEANUP_INTERVAL = 10 # seconds
DEFAULT_OLD_DATA_TRESHOLD = 60 # seconds 
DEFAULT_SEND_INTERVAL = 1 # seconds

class Detector:
    """A class for handling simple detector inputs and outputs"""

    def __init__(self, det_id, det_params, status = None):
        self.det_id = det_id
        self.det_params = det_params
        self.status = status # Will be true or false
        # This is not yet functional
        self.trigger_functions = [] # Functions to trigger if status changes
        
        # NATS STREAM
        stream_params = det_params.get('stream', {})
        if not stream_params:
            print(f"Detector {det_id} is missing stream params".format(det_id))
            return None
        
        if stream_params['connection'] == 'nats':
            if 'nats_subject' in stream_params:
                self.nats_subject = stream_params['nats_subject']
                self.nats = True
            else:
                self.nats = False
                print(f"Detector {det_id} is missing nats_subject".format(det_id))
        else:
            self.nats = False
        self.data = []
        self.data_subject = "detector.data." + self.det_id
        # Detector stats
        self.rising_edge_cnt = 0
        self.falling_edge_cnt = 0
        if det_params.get('type', False) == 'falling_edge':
            self.type = 'falling_edge'
        elif det_params.get('type', False) == 'rising_edge':
            self.type = 'rising_edge'
        else:
            print(f"Detector {det_id} is missing type".format(det_id))
        # For temporarily blocking counting
        # e.g. we might want no to count outgoing vehicles when signal is red
        # (likely an error in the detector)
        self.counting_blocked = False

    def __str__(self):
        return "Detector: {} - {}".format(self.det_id, self.status)
    
    def set_counting_blocked(self, blocked):
        """Sets the counting blocked status"""
        self.counting_blocked = blocked
    
    # Basic data access functions
    def add_data(self, data):
        """Adds data to the radar"""
        if self.counting_blocked:
            return
        # Sort the data by received timestamp
        data_sorted = sorted(self.data, key=lambda x: x['data_received'])
        self.data = data_sorted
        # update the status
        if len(self.data) > 0:
            if data['loop_on'] and not self.data[-1]['loop_on']:
                self.rising_edge_cnt += 1
            if not data['loop_on'] and self.data[-1]['loop_on']:
                self.falling_edge_cnt += 1
        elif len(self.data) == 0:
            if self.data[-1]['loop_on']:
                self.rising_edge_cnt += 1
            
        self.data.append(data)
            # I believe that this is misleading, because the 
            # simulator sends loop down for all in the beginning
            #else:
            #    self.falling_edge_cnt += 1

    def remove_old_data(self, treshold=DEFAULT_OLD_DATA_TRESHOLD):
        "Removes all data with sent timestamp older than treshold"
        now = datetime.datetime.now()
        for data in self.data:
            if 'data_sent' in data:
                data_sent = data['data_sent']
                diff = now - data_sent
                if diff.total_seconds() > treshold:
                    self.data.remove(data)
 
    def get_last_data(self):
        """Returns the last data item"""
        if len(self.data) == 0:
            return None
        return self.data[-1]
    
    def get_vehicle_count(self):
        """Returns the number of passed, based on edge setup"""
        if self.type == 'falling_edge':
            return self.falling_edge_cnt
        elif self.type == 'rising_edge':
            return self.rising_edge_cnt
        else:
            return None        

    # Not used at the moment
    def set_status(self, status):
        """Sets the status of the detector"""
        if self.status != status:
            # This is not yet functional
            for func in self.trigger_functions:
                func(status)
            print("Detector: {} - {}".format(self.det_id, status))

        self.status = status

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

    # ASYNC functions
    async def cleanup_old_data(self):
        """Removes old data, this should be a separate task running at alla times"""
        while True:
            await asyncio.sleep(DEFAULT_CLEANUP_INTERVAL)
            self.remove_old_data()

    async def nats_callback(self, msg):
        """The callback function for the nats and is assigned to the subscription"""
        subject = msg.subject
        reply = msg.reply
        data = msg.data.decode()
        #print(f"Received a message on '{subject} {reply}': {data}")
        data_dict = json.loads(data)
        #if data_dict['id'] == 'detector.status.R8KU':
        #print(f"Received a message on '{subject} {reply}': {data}")
        
        if 'tstamp' in data_dict:
            tstamp = data_dict['tstamp']
            #tstamp_in_datetime = datetime.datetime.fromtimestamp(tstamp/1000)
            if '.' in tstamp:
                split_by_dot = tstamp.split(".")
                tstamp = split_by_dot[0] + "." + split_by_dot[1][:6] # Remove the last digits
            tstamp_in_datetime = datetime.datetime.fromisoformat(tstamp) # Note: this is different from radar
            tstamp_now = datetime.datetime.now()
            data_dict['data_sent'] = tstamp_in_datetime
            data_dict['data_received'] = tstamp_now
        self.add_data(data_dict)

    # Testing dunction for sending data
    async def send_data(self, nats):
        """Send the queue lengths to the nats"""
        while True:
            await asyncio.sleep(DEFAULT_SEND_INTERVAL)
            data = {}
            stored_data = []
            # Make a deep copy of the  data
            for d in self.data:
                stored_data.append(dict(d))
            #print(stored_data)
            for d in stored_data:
                d['data_sent'] = d['data_sent'].isoformat()
                d['data_received'] = d['data_received'].isoformat()

            data['det_id'] = self.det_id
            data['stored_data'] = stored_data
            data['tstamp'] = datetime.datetime.now().timestamp() * 1000
            #await nats.publish(self.data_subject, json.dumps(data).encode())
            #print(f"Sent det data from {self.det_id}: {data}")


class DetectorLogic(Detector):
    """A class for creating new detectors by combining imputs from existing detectors"""
    def __init__(self, det_id, params, status = None):
        super().__init__(det_id, params, status)
    
    def __str__(self):
        return "DetLogic: {} - {}".format(self.det_id, self.status)
    

