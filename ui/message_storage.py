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


    def add_message(self, channel, message):
        #print(f"MessageStorage.add_message: channel={channel}, message={message}")

        channel_prefix = channel.split(".")[0]
        if channel_prefix == DETECTOR_MESSAGE_PREFIX:
            self.add_detector_message(channel, message)
        elif channel_prefix == GROUP_MESSAGE_PREFIX:
            self.add_group_message(channel, message)

    def add_detector_message(self, channel, message):
        det_id = channel.split(".")[2]
        msg_dict = json.loads(message)
        msg_dict["raw_message"] = message
        self.detector_messages[det_id] = DetectorMessage(**msg_dict)
        
    def add_group_message(self, channel, message):
        group_id = channel.split(".")[2]
        msg_dict = json.loads(message)
        msg_dict["raw_message"] = message
        self.group_messages[group_id] = GroupMessage(**msg_dict)


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
        for group in self.group_messages:
            all_messages[group] = self.group_messages[group].__dict__
        df = pd.DataFrame.from_dict(all_messages)
        df = df.transpose()
        df = df.sort_values(by=['id_number'], ascending=True) 
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
        self.id_number = int(id.split(".")[2])
        self.raw_message = raw_message
    
    def __str__(self):
        return f"GroupMessage: id={self.id}, tstamp={self.tstamp}, substate={self.substate}"
    
    def get_raw_message(self):
        return self.raw_message


if __name__ == "__main__":
    print("MessageStorage test")
    asyncio.run(test())

