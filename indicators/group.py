"This unit cointains signal group handlers"
# Note: A lot of cunctionality is the same for many types, 
# maybe we should inherit these

import datetime
import json


# Note: should be configureable
DEFAULT_CLEANUP_INTERVAL = 10 # seconds
DEFAULT_OLD_DATA_TRESHOLD = 60 # seconds 
DEFAULT_SEND_INTERVAL = 1 # seconds

class Group:
    """A class for handling signal groups"""

    def __init__(self, group_id, group_params):
        self.group_id = group_id
        self.group_params = group_params
        self.data = []
        self.substate = ""
        self.is_red_b = None

        #NATS STREAM
        stream_params = group_params.get('stream', {})
        if not stream_params:
            print(f"Group {group_id} is missing stream params".format(group_id))
            return None
        
        if stream_params['connection'] == 'nats':
            if 'nats_subject' in stream_params:
                self.nats_subject = stream_params['nats_subject']
                self.nats = True
            else:
                self.nats = False
                print(f"Detector {group_id} is missing nats_subject".format(group_id))
        else:
            self.nats = False


    def __str__(self):
        return "Group: {}".format(self.group_id)
    
    def add_data(self, data):
        """Adds data to the group"""
        #print(f"Group {self.group_id} got data: {data}")
        self.data.append(data)

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
        """Returns the last data"""
        if len(self.data) == 0:
            return None
        return self.data[-1]

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
        if 'tstamp' in data_dict:
            tstamp = data_dict['tstamp']
            #tstamp_in_datetime = datetime.datetime.fromtimestamp(tstamp/1000)
            tstamp_in_datetime = datetime.datetime.fromisoformat(tstamp) # Note: this id different from radar
            tstamp_now = datetime.datetime.now()
            data_dict['data_sent'] = tstamp_in_datetime
            data_dict['data_received'] = tstamp_now
        self.add_data(data_dict)

        self.substate = data_dict['substate']
        if self.substate in ['r']:
            self.is_red_b = True
        else:
            self.is_red_b = False