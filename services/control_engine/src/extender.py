# -*- coding: utf-8 -*-
"""The Extender

This module implements detecors for signal groups
This is a separate from the SignalGroup in order to make
it easier to implement external control schemes

"""
# Copyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

from signal_group import SignalGroup
import keyboard, time


def main():
    print('Testing the ext')
    #ext = Extender('det0', conf)
    #print(det)

def keyboard_break(ch):
    while not(keyboard.is_pressed('g')):
        time.sleep(0.01)        
    print('Demo continued: ')


class StaticExtender:
    """This creates an extender that is always on or always on/off"""
    def __init__(self, do_extend):
        self.extend = do_extend

    def tick(self):
        pass


class Extender:
    """docstring for Detector"""
    def __init__(self, timer, group, dets, grpdets, e3dets, ext_params): # DBIK200803, add e3dets
        self.system_timer = timer
        self.group = group
        self.grpdets = []
        self.dets = dets
        self.e3dets = e3dets
        self._extend = False  # This is requested by the group
        self.conf_groups = [] # List of conflicting signal grooups
        self.vehcount = 0
        self.conf_sum = 0
        self.threshold = 0.25
        self.momentum = 0
        
        # DBIK202502 Safety extender variables
        self.ext_ended_at = 0
        self.ext3_status = 0
        self.prev_status = 0

        self.ext_mode = 3
        if 'ext_mode' in ext_params:
            self.ext_mode = ext_params['ext_mode']
            BP = 1

        self.ext_threshold = 0.25
        if 'ext_threshold' in ext_params:
            self.ext_threshold = ext_params['ext_threshold']
            BP = 1

        self.time_discount = 60
        if 'time_discount' in ext_params:
            self.time_discount = ext_params['time_discount']
            BP = 1


        self.safety_ext = False
        if 'safety_ext' in ext_params:
            self.safety_ext = ext_params['safety_ext']
            BP = 1
        self.safety_time = 0
        if 'safety_time' in ext_params:
            self.safety_time = ext_params['safety_time']
            BP = 1
                
        for grp in self.group.conflicting_groups:
            self.conf_groups.append(grp) 
            print('conf group added: ',grp)

        print('Extender, group: ',self.group.group_name, 'Conf groups: ', self.conf_groups)

        """"
        for det in dets:
            dgr = det.group
            grn = group.group_name
            if det.group == group.group_name:
                self.dets.append(det)
                DB =1 """
        
        self.grpdets = []
        #for gdet in grpdets:   # DBIK231216 Add signal group extenders
            #if gdet.group == group.group_name:
            #    self.grpdets.append(gdet)

        self.group_name = group.name
        
        #Set this object as group extender
        if dets != []:
            group.extender = self
        if e3dets != []:
            group.e3extender = self



    def __str__(self):
        return "Ext for group:{}, dets:{}".format(self.group.group_name, self.dets)

    def __repr__(self):
        return "Ext<{}>".format(self.group)

    def update_extension(self):
        """Function updates the extension status to the group"""
        for det in self.dets:
            if det.is_extending():
                self.extend = True # read by the group
                return
        for qdet in self.grpdets:    # DBIK231216 added group extenders
            if qdet.is_extending():
                self.extend = True 
                return
        self.extend = False # No det extends

    def tick(self):
        self.update_extension()

    """"
    @property
    def extend(self):
        return self._extend

    @extend.setter
    def extend(self, setted_extend):
        # Phase commands the green to end -> phase has used the green of previus phase
        self._extender = setted_extend
    
        """

# This is a new extender type using the e3-detectors as input #DBIK240731
class e3Extender(Extender):

    def update_extension(self):
        """Function updates the extension status to the group"""
        
        self.conf_sum = 0
    
        # Calculate the Red-side pressure 
        for grp in self.conf_groups:
            if grp['group'].e3extender:
                self.conf_sum += grp['group'].e3extender.vehcount
        
        # Calculate the Green-side Momentum, old version
        vc = 0
        for e3det in self.e3dets:
             vc += e3det.veh_count()
        self.vehcount = vc

        # DBIK20250409 Calculate the Green-side Momentum, take signal state in account
        mm = 0
        for e3det in self.e3dets:
             mm += e3det.momentum2()
        self.momentum = mm

        if (self.conf_sum == 0) and (self.vehcount == 0):
            e3det.extend_on = False
            self.extend = False # No det extends
            return 0

        # Decide about green extension
        if self.ext_mode == 1:
            self.threshold = self.ext_threshold
            if self.vehcount > self.threshold:
                self.extend = True 
                e3det.extend_on = True
                return 1
            
        elif self.ext_mode == 2:
            if self.conf_sum > 0:   
                traffic_ratio = self.vehcount/self.conf_sum
                self.threshold = self.ext_threshold
                if traffic_ratio > self.threshold:
                    self.extend = True 
                    e3det.extend_on = True
                    return 1
            else: 
                self.extend = True 
                e3det.extend_on = True
                return 1

        elif self.ext_mode == 3:
            if self.conf_sum > 0:   
                GreenTimeUsed = self.system_timer.seconds - self.group.green_started_at
                TimeDiscount = 1.0 + (GreenTimeUsed/self.time_discount)
                traffic_ratio = self.vehcount/self.conf_sum  # DBIK20250409 replace vehcount with momentum
                self.threshold = self.ext_threshold * TimeDiscount
                if traffic_ratio > self.threshold:
                    self.extend = True 
                    e3det.extend_on = True
                    return 1
            else: 
                self.extend = True 
                e3det.extend_on = True
                return 1
            
        elif self.ext_mode == 4:
            if self.conf_sum > 0:   
                GreenTimeUsed = self.system_timer.seconds - self.group.green_started_at
                TimeDiscount = 1.0 + (GreenTimeUsed/self.time_discount)
                traffic_ratio = self.momentum/self.conf_sum  # DBIK20250409 replace vehcount with momentum
                self.threshold = self.ext_threshold * TimeDiscount
                if traffic_ratio > self.threshold:
                    self.extend = True 
                    e3det.extend_on = True
                    return 1
            else: 
                self.extend = True 
                e3det.extend_on = True
                return 1
        
        e3det.extend_on = False
        self.extend = False # No det extends
        return 0


    def update_safety_extension(self):
        safety_ext_time = self.system_timer.seconds - self.ext_ended_at
        ShortGap = False
        for e3det in self.e3dets:      
            if e3det.ShortGapFound:
                ShortGap = True

        if (safety_ext_time < 10.0) and ShortGap: 
            for e3det in self.e3dets:
                e3det.SafeExtOn = True

            # Demo features
            # keyboard_break('g')
            # while not(keyboard.is_pressed('g')):
            # time.sleep(0.2)        
            # print('Demo continued: ')

            return 3
        else:
            for e3det in self.e3dets:
                e3det.SafeExtOn = False
            print('Signal X: Safety extension of ', round(safety_ext_time,1), ' seconds ended at: ',round(self.system_timer.seconds,1))
            # Demo feature
            # time.sleep(1.00) 
            return 4


    def tick(self):

        # DBIK20250213 Safety extension update added
        self.prev_status = self.ext3_status
        
        if (self.group.name == 'group11: '):
            DB1 = 1 
        
        if self.ext3_status in [0,1,4]:
            self.ext3_status = self.update_extension()
        else:
            self.ext3_status = self.update_safety_extension()
        
        if (self.safety_ext) and (self.group.state=='Green_Extending'):  
            if (self.prev_status==1) and (self.ext3_status==0): 
                self.ext_ended_at = self.system_timer.seconds
                self.ext3_status=2     
                print('Signal X: Basic ext ended at: ',round(self.ext_ended_at,1))
            
        self.extend = (self.ext3_status in [1,2,3])
        for e3det in self.e3dets:
            e3det.extend_on = self.extend

        # self.update_extension()

    
    @property
    def extend(self):
        return self._extend

    @extend.setter
    def extend(self, setted_extend):
        # Phase commands the green to end -> phase has used the green of previus phase
        # self._extender = setted_extend  
        self._extend = setted_extend   # DBIK240803 _extender -> _extend
    
    

if __name__ == "__main__":
    main()

