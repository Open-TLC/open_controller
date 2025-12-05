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
        if self.type in ['request','extender','e3detector', 'prio','ext_extender']:
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
        if 'v2x-on' in conf: 
            self.v2x_ON = conf['v2x-on']
            print('V2X-detector: ', name,' V2X-ON: ', self.v2x_ON)
            BP = 1
        else:
            self.v2x_ON = False
        
        self.owngroup_obj = None

        self.extgroup_obj = None
        self.extgroup_name = '' 

        self.extend_on = False

        self.det_vehicles_dict = {}
        self.last_vehicles_dict = {}

         # DBIK202502 Variables for safety green extension
        self.MinOZ = 40.0
        self.MaxOZ = 120.0
        self.SafeDist = 30.0
        self.SafeExtOn = False
        self.ShortGapFound = False
        




    def __str__(self):
        return "Det:{}, conf:{}".format(self.name, self.conf)

    def __repr__(self):
        return "<{}>".format(self.name)

    def get_params(self):
        """Returns the detector parameters"""
        return self.conf


    def set_request_groups(self, list_of_groups):
        """Init script for mapping dets to group-objects"""

        
        # if not self.type in ['request',"e3detector"]:
        if not self.type in ['request']: 
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

class Ext_Extender(ExtDetector):
    """Detector for extending"""
    def __init__(self, system_timer, name, conf):
        super(ExtDetector, self).__init__(system_timer, name, conf)
        self.group = conf['group']
        self.ext_time = conf['ext_time']

    def is_extending(self):
        """Returns true if detector on """  
        return self.loop_on 

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
        self.speedsum = 0
        
    def is_extending(self):
        """Returns true if vehicle count is more than zero"""
        return self.veh_count(self) > 0
    
  
    def tick(self):  # DBIK250428 This should not be called unless multi-sumo mode
        """ Updating of e3-detector"""
        # e3vehlist = traci.multientryexit.getLastStepVehicleIDs(self.sumo_id) 
        # self.update_e3_vehicles(e3vehlist)
        return  


    # We update the vehlist from e3 message
    def update_e3_vehicles(self, obj_list):
        """updates the vehlist from e3 message"""
        self.det_vehicles_dict = obj_list
        self.vehcount = len(self.det_vehicles_dict)
        self.ShortGapFound = False  # DBIK20250312
        self.speedsum = 0

        for vehid in self.det_vehicles_dict:

            vtype = self.det_vehicles_dict[vehid]['vtype']
            speed = self.det_vehicles_dict[vehid]['speed']  # DBIK202508 Key error ?
            self.speedsum += speed                      
            # TLSdist = self.det_vehicles_dict[vehid]['TLSdist']  # DBIK202508 Key error ?
            # TLSno = self.det_vehicles_dict[vehid]['TLSno']
            
            if (vtype == 'car_type'):
                pass
            elif vtype == 'truck_type':
                self.vehcount +=2 # DBIK240923 Add extra weight for trucks 1 truck = 3 vehs
                # print('vehtype : ', type)
            elif  vtype == 'tram_type':
                self.vehcount +=100
            elif  vtype == 'bike_type':
                self.vehcount += 0
                if self.name == "e3d16m30":
                    BP1 = 1
                    self.owngroup_obj.request_green = True 
                    # self.loop_on = True  # DBIK 202511 Let AI-cam to set request
                    #   pass
            
            # Special setting for JS270T, should be configured in init-file DBIK20241025
            elif (vtype == 'tram_R9'):
                if (self.owngroup_name == 'group4'):
                    self.vehcount +=100            
            elif (vtype == 'tram_R7'):
                if (self.owngroup_name == 'group8'):
                    self.vehcount +=100

            elif (vtype == 'v2x_type'):
                if self.v2x_ON:                 
                    self.det_vehicles_dict[vehid]['vcolor'] = 'blue'  # V2X vehicle detected   
                    if (TLSno == 11) and (TLSdist < self.MaxOZ) and (TLSdist > self.MinOZ):  
                        self.det_vehicles_dict[vehid]['vcolor'] = 'green'  # V2X veh at option-zone

                        leaderDist = self.det_vehicles_dict[vehid]['leaderDist']
                        if (leaderDist < self.SafeDist) and (leaderDist > 0):
                            self.det_vehicles_dict[vehid]['vcolor'] = 'yellow'   # V2X veh too close to vehicle in front
                            self.ShortGapFound = True
            
                            if self.SafeExtOn:
                                self.det_vehicles_dict[vehid]['vcolor'] = 'red'    # Safety extension ON for V2X veh
                                curspeed = self.det_vehicles_dict[vehid]['vspeed']
                                
                                leaderSpeed = self.det_vehicles_dict[vehid]['leaderSpeed']
                                VX2newSpeed = leaderSpeed - 5.0
                                VX2newSpeed = 10.0
                                if VX2newSpeed > 4.0:
                                    self.det_vehicles_dict[vehid]['vspeed'] = VX2newSpeed   # V2X vehicle slow down
                                    
                        else: pass 

            else:
                print('**************** Error in vehicle type: ', vtype)
            
            COORD = True
            if COORD: 
                if "Sat2Ramp" in vehid:
                    self.vehcount +=100
                
                # elif "Ramp2Sat" in vehid:
                #    self.vehcount +=100

    def veh_count(self):
        return self.vehcount
    
    def momentum1(self):
        if self.owngroup_obj.group_on():
            mm = self.vehcount
        else: mm = 0
        return mm
    
    def momentum2(self):
        if self.vehcount > 0:
            avr_speed = self.speedsum/self.vehcount
            if avr_speed < 0.2:
                return 0
            else:
                return self.vehcount
        else: 
            return 0
    

        

if __name__ == "__main__":
    main()

