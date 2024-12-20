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


def main():
    print('Testing the ext')
    #ext = Extender('det0', conf)
    #print(det)


class StaticExtender:
    """This creates an extender that is always on or always on/off"""
    def __init__(self, do_extend):
        self.extend = do_extend

    def tick(self):
        pass


class Extender:
    """docstring for Detector"""
    def __init__(self, timer, group, dets, grpdets, e3dets): # DBIK200803, add e3dets
        self.system_timer = timer
        self.group = group
        self.grpdets = []
        self.dets = dets
        self.e3dets = e3dets
        self._extend = False  # This is requested by the group
        self.conf_groups = [] # List of conflicting signal grooups
        self.vehcount = 0
        self.conf_sum = 0
        self.threshold = 0.3
        self.ext_mode = 2
        
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
        Threshold1 = 0
        Threshold2 = 0.5
        Threshold3 = 0.3
        MaxGreen = 60 
        self.conf_sum = 0
    
        # Calculate the Red-side pressure 
        for grp in self.conf_groups:
            if grp['group'].e3extender:
                self.conf_sum += grp['group'].e3extender.vehcount
        
        # Calculate the Green-side Momentum
        vc = 0
        for e3det in self.e3dets:
             vc += e3det.veh_count()
        self.vehcount = vc

        if (self.conf_sum == 0) and (self.vehcount == 0):
            e3det.extend_on = False
            self.extend = False # No det extends
            return

        # Decide about green extension
        if self.ext_mode == 1:
            self.threshold = Threshold1
            if self.vehcount > Threshold1:
                self.extend = True 
                e3det.extend_on = True
                return
            
        elif self.ext_mode == 2:
            if self.conf_sum > 0:   
                traffic_ratio = self.vehcount/self.conf_sum
                self.threshold = Threshold2
                if traffic_ratio > self.threshold:
                    self.extend = True 
                    e3det.extend_on = True
                    return
            else: 
                self.extend = True 
                e3det.extend_on = True
                return

        elif self.ext_mode == 3:
            if self.conf_sum > 0:   
                GreenTimeUsed = self.system_timer.seconds - self.group.green_started_at
                TimeDiscount = 1.0 + (GreenTimeUsed/MaxGreen)
                traffic_ratio = self.vehcount/self.conf_sum
                self.threshold = Threshold3 * TimeDiscount
                if traffic_ratio > self.threshold:
                    self.extend = True 
                    e3det.extend_on = True
                    return
            else: 
                self.extend = True 
                e3det.extend_on = True
                return
        
        e3det.extend_on = False
        self.extend = False # No det extends


    def tick(self):
        self.update_extension()

    
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

