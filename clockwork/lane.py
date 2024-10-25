# -*- coding: utf-8 -*-
"""The signal lane module.

This module implements the lane set up for the controller

"""
# Copyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

import json

TEST_CONF = "./testmodel/nats_controller.json"

def testing():
    print("Testing")
    from confread import GlobalConf

    sys_cnf = GlobalConf(filename=TEST_CONF).cnf
    lanes_conf = sys_cnf['controller']['lanes']
    lanes = []
    for lane_id, lane_conf in lanes_conf.items():
        lane_conf['id'] = lane_id
        lane = Lane(lane_conf)
        lanes.append(lane)
    print(lanes)

class Lane:
    def __init__(self, lane_config):
        """Constructor for the Lane class
            As a parameter we get a dictionary with the following keys:
            id: The id of the lane
            length: The length of the lane
            coordinates: A list of coordinates for the lane
            sumo_id: The id of the lane in sumo
            URI: The URI for the lane
            users: A list of users for the lane (eg. car, bus, bike, pedestrian)
        """
        #self.id = lane_config.get('id')
        self.coordinates = lane_config.get('coordinates', [])
        self.sumo_id = lane_config.get('sumo_id', None)
        self.id = lane_config.get('id', None) # Should be random value?
        self.URI = lane_config.get('URI', None)
        self.users = lane_config.get('users', [])
        self.length = lane_config.get('length', 0)
        self.street = lane_config.get('street', None)
        self.direction = lane_config.get('direction', None)


    def __repr__(self):
        return "Lane: " + self.sumo_id

    
    def __str__(self):
        return "Lane: " + self.sumo_id + ": " + str(self.coordinates)


    def get_params(self):
        return self.__dict__

    def get_json(self):
        return json.dumps(self.__dict__, indent=4, sort_keys=True)
    
        
if __name__ == "__main__":
    testing()