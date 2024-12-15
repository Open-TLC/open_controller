# -*- coding: utf-8 -*-
"""The message storage module.

This module contains the message storage class. This is intended to be used fpr stpring all the latess
messages on a given NATS channel(s). This is for UI to handle the messages sent by different entities


"""
# Copyright 2023 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

import asyncio
import pandas as pd
from nats.aio.client import Client as NATS
import json

DETECTOR_MESSAGE_PREFIX = "detector"
GROUP_MESSAGE_PREFIX = "group"
E3_DETECTOR_MESSAGE_IDENTIFIER = "e3"
NATS_SERVER = "localhost:4222"

async def test():
    ip = "localhost"
    port = 4222
    nats = NATS()
    await nats.connect(NATS_SERVER)
    storage = MessageStorage()

    async def cb(msg):
        #print(f"Message received: {msg.subject} - {msg.data.decode()}")
        storage.add_message(msg.subject, msg.data.decode())

    await nats.subscribe("detector.status.*", cb=cb)
    await nats.subscribe("group.status.*.*", cb=cb)
   

    while True:
        await asyncio.sleep(1)
        #print("**")
        #print(storage.get_detector_messages())
        #print(storage.get_detector_messages_as_df())
        print(storage.get_group_messages_as_df())

class MessageStorage:
    def __init__(self):
        self.detector_messages = {}
        self.group_messages = {}
        self.e3_messages = {}

    def add_message(self, channel, message):
        #print(f"MessageStorage.add_message: channel={channel}, message={message}")

        channel_prefix = channel.split(".")[0]
        if channel_prefix == DETECTOR_MESSAGE_PREFIX:
            self.add_detector_message(channel, message)
        elif channel_prefix == GROUP_MESSAGE_PREFIX:
            second_part = channel.split(".")[1]
            if second_part == E3_DETECTOR_MESSAGE_IDENTIFIER:
                self.add_e3_det_message(channel, message)
            else:
                self.add_group_message(channel, message)
        print(E3_DETECTOR_MESSAGE_IDENTIFIER)

    def add_detector_message(self, channel, message):
        det_id = channel.split(".")[2]
        msg_dict = json.loads(message)
        msg_dict["raw_message"] = message
        self.detector_messages[det_id] = DetectorMessage(**msg_dict)
        
    def add_group_message(self, channel, message):
        group_id = channel.split(".")[-1]
        msg_dict = json.loads(message)
        msg_dict["raw_message"] = message
        self.group_messages[group_id] = GroupMessage(**msg_dict)

#3719] Received on "group.e3.270.1"
#{"count": 1, "radar_count": 0, "det_vehcount": 1, "group_substate": "G", "view_name": "group1_view", 
# "objects": {"38e7299a-f2b0-4185-ae14-ddcbc7abf99c": 
# {"speed": 10, "vtype": "car_type", "sumo_id": null, "source": "detector_count", "notes": "Speed and types are default values"}}, 
# "offsets": {"Group 1 lane 1": -7}, "tstamp": 1734278972620.2341}


    def add_e3_det_message(self, channel, message):
        """Adds a message from the E3 detector"""
        msg_dict = json.loads(message)
        new_dict = {}
        new_dict['view_name'] = msg_dict['view_name']
        new_dict['radar_count'] = msg_dict['radar_count']
        new_dict['det_vehcount'] = msg_dict['det_vehcount']
        new_dict['group_substate'] = msg_dict['group_substate']
        #new_dict['raw_message'] = msg_dict
        self.e3_messages[new_dict['view_name']] = E3Message(**new_dict)


    def get_detector_messages(self):
        return self.detector_messages



    def get_latest_messages(self):
        raw_messages = []
        for key in self.detector_messages:
            raw_messages.append(self.detector_messages[key].get_raw_message())
        
        msg_out = "Dets: " + str(raw_messages) + '\n'

        raw_messages = []
        for key in self.group_messages:
            raw_messages.append(self.group_messages[key].get_raw_message())
        msg_out += " Groups: " + str(raw_messages)

        return msg_out


    def get_detector_messages_as_df(self):
        "Returns all detector messages as a dataframe (for table in UI)"
        all_messages = {}
        for det in self.detector_messages:
            all_messages[det] = self.detector_messages[det].__dict__
        df = pd.DataFrame.from_dict(all_messages)
        df = df.transpose()
        #cols = df.columns.tolist()
        return df



    def get_group_messages_as_df(self):
        "Returns all group messages as a dataframe (for table in UI)"
        all_messages = {}
        # No messages
        if self.group_messages == {}:
            return pd.DataFrame()
        
        for group in self.group_messages:
            all_messages[group] = self.group_messages[group].__dict__
        df = pd.DataFrame.from_dict(all_messages)
        df = df.transpose()
        df = df.sort_values(by=['id_number'], ascending=True) 
        #cols = df.columns.tolist()
        return df

    def get_e3_messages_as_df(self):
        "Returns all E3 messages as a dataframe (for table in UI)"
        all_messages = {}
        if self.e3_messages == {}: 
            return pd.DataFrame()
        
        for e3 in self.e3_messages:
            all_messages[e3] = self.e3_messages[e3].__dict__
        df = pd.DataFrame.from_dict(all_messages)
        df = df.transpose()
        #cols = df.columns.tolist()
        return df

        
class DetectorMessage:
    def __init__(self, id=None, tstamp=None, loop_on=None, raw_message=""):
        self.id = id
        self.tstamp = tstamp
        self.loop_on = loop_on
        self.raw_message = raw_message
    
    def __str__(self):
        return f"DetectorMessage: id={self.id}, tstamp={self.tstamp}, loop_on={self.loop_on}"
    
    def get_raw_message(self):
        return self.raw_message

class GroupMessage:
    def __init__(self, id=None, tstamp=None, substate=None, raw_message=""):
        self.id = id
        self.tstamp = tstamp
        self.substate = substate
        self.id_number = id.split(".")[2]
        self.raw_message = raw_message
    
    def __str__(self):
        return f"GroupMessage: id={self.id}, tstamp={self.tstamp}, substate={self.substate}"
    
    def get_raw_message(self):
        return self.raw_message
class E3Message:
    def __init__(self, view_name=None, radar_count=None, det_vehcount=None, group_substate=None):
        self.view_name = view_name
        self.radar_count = radar_count
        self.det_vehcount = det_vehcount
        self.group_substate = group_substate

    def __str__(self):
        return f"E3Message: view_name={self.view_name}, radar_count={self.radar_count}, det_count={self.det_count}, group_substate={self.group_substate}"
    
    def get_raw_message(self):
        return self.raw_message

if __name__ == "__main__":
    print("MessageStorage test")
    asyncio.run(test())

