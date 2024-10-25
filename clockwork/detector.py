# -*- coding: utf-8 -*-
"""The detector.

This module implements detecors for traffic controllers

"""
# Copyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#
#import traci
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
        if self.type in ['request','extender','e3detector']:
            self.sumo_id = conf['sumo_id']
        else:
            self.sumo_id = None
        self.detection_at = 0  # detection start time in seconds
        self.detection_end_at = 0  # detection end time, extension countdown start
        if self.type == 'request':
            names = conf['request_groups']
            self.owngroup_name = names[0]
        else: self.owngroup_name = conf['group']
        
        self.owngroup_obj = None

        self.extgroup_obj = None
        self.extgroup_name = '' 

        self.extend_on = False
        

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
                grp.request_green = True  # DBIK231213 Note: req turned ON ny pulse up only, to be reseted by group after served
                if grp.group_name == 'group1':
                    BP = 1
                # if grp.group_red_started() and self._loop_on:
                #    grp.request_green = True  # DBIK231213 If the detector stays on over the group red time, the request has to be set again
        if not set_on and self._loop_on:
            self.pulse_down()

        #if set_on:
        #    for grp in self.request_groups:
        #        grp.request_green = True  # Note: req turned off by group after served
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
        self.last_veh_list = []

    def is_extending(self):
        """Returns true if vehicle count is more than zero"""
        return self.veh_count(self) > 0
    
    def tick(self):  # DBIK240801 tick for e3 detector
        """ """
        self.vehcount = traci.multientryexit.getLastStepVehicleNumber(self.sumo_id) 
        e3vehlist = traci.multientryexit.getLastStepVehicleIDs(self.sumo_id)
        
        for vehid in e3vehlist:
            len = traci.vehicle.getLength(vehid)
            if len > 10.0:
                self.vehcount +=2 # DBIK240923 Add extra weight for trucks 1 truck = 3 vehs

    
        # self.indicate_main_signal_state(e3vehlist,self.last_veh_list)  
        # self.indicate_sub_signal_state(e3vehlist,self.last_veh_list)      
        self.indicate_req_perm_state(e3vehlist,self.last_veh_list)   

        self.last_veh_list = e3vehlist


    def indicate_main_signal_state(self,vehlist,lastlist):

        owngroup = self.owngroup_obj

        # DBIK202408  Set color of vehicles leaving the e3detector   
        for vehid in lastlist:
            if not(vehid in vehlist):
                try:
                    self.set_vehicle_color(vehid,'gray')
                except:
                    self.errorcount += 1
        
        # DBIK20240905
        if self.errorcount > 0:
            DB = self.errorcount
        
        # DBIK202408  Set color of vehicles at the e3detector when the signal state changes
        if owngroup.group_main_state_changed('Green',owngroup.state,owngroup.prev_state):
            for vehid in vehlist:
                self.set_vehicle_color(vehid,'green')
        elif owngroup.group_main_state_changed('Red',owngroup.state,owngroup.prev_state):
            for vehid in vehlist:
                self.set_vehicle_color(vehid,'red')

        # DBIK202408  Set color of vehicles entering e3detector
        for vehid in vehlist:
            if not(vehid in lastlist): # a vehicle entering
                if owngroup.group_green_or_amber():
                    self.set_vehicle_color(vehid,'green')
                else:
                    self.set_vehicle_color(vehid,'red')

    def indicate_sub_signal_state(self,vehlist,lastlist):

        owngroup = self.owngroup_obj

        # DBIK202408  Set color of vehicles leaving the e3detector   
        for vehid in lastlist:
            if not(vehid in vehlist):
                try:
                    self.set_signal_state_to_vehice_color(vehid,'Out')
                except:
                    self.errorcount += 1
        
            # if not(vehid in vehlist):
                # self.set_signal_state_to_vehice_color(vehid,'Out')
        
        # DBIK202408  Set color of vehicles at the e3detector when the signal state changes
        og_state = owngroup.group_sub_state_changed('Any',owngroup.state,owngroup.prev_state)
        if og_state != 'None':
            for vehid in vehlist:
                self.set_signal_state_to_vehice_color(vehid,og_state)

        for vehid in vehlist:       
            if not(vehid in lastlist): # a new vehicle entering
                self.set_signal_state_to_vehice_color(vehid,self.owngroup_obj.state)


    def indicate_req_perm_state(self,vehlist,lastlist):

        owngroup = self.owngroup_obj

        # DBIK202408  Set color of vehicles leaving the e3detector   
        for vehid in lastlist:
            if not(vehid in vehlist):
                try:
                    self.set_req_perm_to_vehice_color(vehid,'Out',owngroup)
                except:
                    self.errorcount += 1
        
            # if not(vehid in vehlist):
                # self.set_signal_state_to_vehice_color(vehid,'Out')
        
        # DBIK202408  Set color of vehicles at the e3detector when the signal state changes
        og_state = owngroup.group_sub_state_changed('Any',owngroup.state,owngroup.prev_state)
        if og_state != 'None':
            for vehid in vehlist:
                self.set_req_perm_to_vehice_color(vehid,og_state, owngroup)

        for vehid in vehlist:       
            if not(vehid in lastlist): # a new vehicle entering
                self.set_req_perm_to_vehice_color(vehid,self.owngroup_obj.state, owngroup)


    def set_vehicle_color(self,vehid,vcolor):

        if vcolor == "red":
            traci.vehicle.setColor(vehid,(255,0,0))
        elif vcolor == "darkred":
            traci.vehicle.setColor(vehid,(153,0,0))
        elif vcolor == "darkgreen":
            traci.vehicle.setColor(vehid,(0,102,0))
        elif vcolor == "green":
            traci.vehicle.setColor(vehid,(0,255,0))
        elif vcolor == "gray":
            traci.vehicle.setColor(vehid,(220,220,220))

    
    def set_signal_state_to_vehice_color(self,vehid,sigstate):

        if sigstate in ['Red_MinimumTime','Red_CanEnd']:
            traci.vehicle.setColor(vehid,(153,0,0)) # Dark Red
        elif sigstate in ['Red_ForceGreen']:
            traci.vehicle.setColor(vehid,(255,0,0)) # Red
        elif sigstate in ['Green_MinimumTime']:
            traci.vehicle.setColor(vehid,(0,102,0)) # Dark Green
        elif sigstate in ['Green_Extending']:
            traci.vehicle.setColor(vehid,(0,255,0)) # Green
        elif sigstate in ['Green_RemainGreen','Amber_MinimumTime']:
            traci.vehicle.setColor(vehid,(0,128,255)) # Blue
        elif sigstate in ['Green_RemainGreen']:
            traci.vehicle.setColor(vehid,(0,128,255)) # Blue
        elif sigstate in ['Red_WaitIntergreen','AmberRed_MinimumTime']:
            traci.vehicle.setColor(vehid,(255,0,255)) # Pink
        elif sigstate in ['Out']:
            traci.vehicle.setColor(vehid,(220,220,220)) # Gray


    def set_req_perm_to_vehice_color(self,vehid,sigstate,own_group):

        if sigstate in ['Red_MinimumTime','Red_CanEnd','Red_ForceGreen']:
            if own_group.has_green_request():
                traci.vehicle.setColor(vehid,(153,0,0)) # Dark Red
            else:
                traci.vehicle.setColor(vehid,(255,0,0)) # Red

        if sigstate in ['Red_WaitIntergreen','AmberRed_MinimumTime','Green_MinimumTime','Green_Extending','Green_RemainGreen','Amber_MinimumTime']:
            if own_group.has_green_permission():
                traci.vehicle.setColor(vehid,(0,102,0)) # Dark Green
            else: 
                traci.vehicle.setColor(vehid,(0,255,0)) # Green
        
        if sigstate in ['Out']:
            traci.vehicle.setColor(vehid,(220,220,220)) # Gray
       
    def veh_count(self):
        # self.tick()
        return self.vehcount
        

if __name__ == "__main__":
    main()

