# -*- coding: utf-8 -*-
"""The detector.

This module implements detecors for traffic controllers

"""
# Copyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#
# import traci
from signal_group import SignalGroup
#from timer import Timer


def main():
    print('testing dets')
    conf = {
        'sumo_id':'0',
        'request_groups':['group0', 'group1']
    }
    det = Detector('det0', conf)
    print(det)

class Detector:
    """docstring for Detector"""
    def __init__(self, system_timer, name, conf):
        self.system_timer = system_timer
        self.conf = conf
        self.name = name
        self.type = conf['type']
        self._loop_on = False
        self.request_groups = []
        self.priolevel = 2
        if self.type in ['request','extender','e3detector', 'prio']:
            self.sumo_id = conf['sumo_id']
        else:
            self.sumo_id = None
        self.detection_at = 0  # detection start time in seconds
        self.detection_end_at = 0  # detection end time, extension countdown start
        if self.type in ['request']:
            names = conf['request_groups']
            self.owngroup_name = names[0]
        else: 
            self.owngroup_name = conf['group']
        if 'priority' in conf: 
            self.priolevel = conf['priority']
            print('Priority detector: ', name,' Priority level: ', self.priolevel)
        else:
            self.priolevel = 2
        
        self.owngroup_obj = None

        self.extgroup_obj = None
        self.extgroup_name = '' 

        self.extend_on = False

        self.det_vehicles_dict = {}
        self.last_vehicles_dict = {}

    def __str__(self):
        return "Det:{}, conf:{}".format(self.name, self.conf)

    def __repr__(self):
        return "<{}>".format(self.name)

    def get_params(self):
        """Returns the detector parameters"""
        return self.conf


    def set_request_groups(self, list_of_groups):
        """Init script for mapping dets to group-objects"""
        if not self.type == 'request':
            return False

        for req_grp in self.conf['request_groups']:
            group_found = False
            for group in list_of_groups:
                if req_grp == group.group_name:
                    self.request_groups.append(group)
                    group_found = True
            if not group_found:
                print('Group: {} not found'.format(req_grp))
                return False
        return True

    def pulse_up(self):
        """Detector pulse occupation starts"""
        #if self.type == 'extender':
        self.detection_at = self.system_timer.seconds
        #for grp in self.request_groups:
        #    grp.request_green = True  # Note: req turned off by group after served

    def pulse_down(self):
        """ DBIK 12/22 Detector pulse occupation ends, extension starts"""
        #if self.type == 'extender':
        self.detection_end_at = self.system_timer.seconds

    def keep_request_on(self):   # DBIK 02/2023 Disabled, does not work 
        """Detector status on, keep group request on"""
        #if self.type == 'extender':
        # for grp in self.request_groups:
        #    grp.request_green = True  # Note: req turned off by group after served

        
    @property
    def loop_on(self):
        return self._loop_on

    @loop_on.setter
    def loop_on(self, set_on):
        if set_on and not self._loop_on:
            self.pulse_up()
            for grp in self.request_groups:
                grp.request_green = True  # DBIK231213 Note: req turned ON by pulse up only, to be reseted by group after served
                
                # DBIK202411 Set priority request by detector logic
                grp.own_request_level = self.priolevel # DBIK241029 pass the request priority level to the signal group
                for confgrp in grp.conflicting_groups:  # DBIK241101 pass the request priority level to the conflicting signal groups
                    other_req_level = confgrp['group'].other_request_level
                    if self.priolevel > other_req_level:
                        confgrp['group'].other_request_level = self.priolevel # DBIK201105 Set only if higher request level 
          
                
        if not set_on and self._loop_on:
            self.pulse_down()

        self._loop_on = set_on

    def tick(self):  # DBIK231218 Checking if the green request need to be set ON
        """Setting request ON at red start if the detector states are not changing due to traffic jam"""
        if self._loop_on:
            for grp in self.request_groups:
                if grp.group_red_started():
                    grp.request_green = True 

class ExtDetector(Detector):
    """Detector for extending"""
    def __init__(self, system_timer, name, conf):
        super(ExtDetector, self).__init__(system_timer, name, conf)
        self.group = conf['group']
        self.ext_time = conf['ext_time']

    def is_extending(self):
        """Returns true if detector on OR time passed after pulse down is less than the ext_time"""  
        return self.loop_on or ((self.detection_end_at + self.ext_time) > self.system_timer.seconds)

    def tick(self):  # DBIK240801 
        """tick is doing nothing, but has to defined. Otherwise will inherit from Request detector"""
        pass


# BBIK231214  New detector class for extending by signal groups 
class GrpDetector(Detector):
    """Detector for a group extending extending another group"""
    def __init__(self, system_timer, name, conf):
        super(GrpDetector, self).__init__(system_timer, name, conf)
        # self.group_name = conf['group']
        self.ext_time = conf['ext_time']
        self.extgroup_name = conf['extgroup']

    def is_extending(self):
        """Returns true if extending signal group is green OR time passed after the green start is less than the ext_time"""
        ext_grp_on = self.extgroup.group_on
        if self.extgroup.green_started_at < 0:
            return False
        ext_time_on = (self.extgroup.green_started_at + self.ext_time) > self.system_timer.seconds
        ext_on = ext_time_on
        return ext_on
    
    def tick(self):  # DBIK240801
        """tick is doing nothing, but has to defined. Otherwise will inherit from Request detector"""
        pass
        
# BBIK230731  New detector class for extending based on e3 detectors 
class e3Detector(Detector):
    """Detector for extending"""
    def __init__(self, system_timer, name, conf):
        super(e3Detector, self).__init__(system_timer, name, conf)
        # self.group = conf['group']
        self.vehcount = 0
        self.errorcount = 0
        
    def is_extending(self):
        """Returns true if vehicle count is more than zero"""
        return self.veh_count(self) > 0
    
  
    def tick(self):  # DBIK240801 tick for e3 detector
        """ Updating of e3-detector"""
        
        for vehid in self.det_vehicles_dict:

            vtype = self.det_vehicles_dict[vehid]['vtype']

            if vtype == 'truck':
                self.vehcount +=2 # DBIK240923 Add extra weight for trucks 1 truck = 3 vehs
                # print('vehtype : ', type)
            if  vtype == 'ratikka':
                self.vehcount +=100

            # Special setting for JS270T, should be configured in init-file DBIK20241025
            if (vtype == 'tram_R9'):
                if (self.owngroup_name == 'group4'):
                    self.vehcount +=100            
            if (vtype == 'tram_R7'):
                if (self.owngroup_name == 'group8'):
                    self.vehcount +=100

    # We update the vehlist from e3 message
    def update_e3_vehicles(self, msg_dict):
        """updates the vehlist from e3 message"""
        self.det_vehicles_dict = msg_dict['objects']
        self.vehcount = len(self.det_vehicles_dict)

       
    def veh_count(self):
        # self.tick()
        return self.vehcount
        

if __name__ == "__main__":
    main()

