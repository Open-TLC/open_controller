# -*- coding: utf-8 -*-
"""The traffic controller module.

This module implements the traffic controller for signalgroup based 
control


Design principles:
1)  Each group connected to this unit is independent in operations
2)  Operation is not based on "phases" as such but merely phasering that 
    gives preference order of next groups to start
3). The "preference" order is scanned based on requests, finding the next 
    main phase with a request
4)  Controller simply gives permissions to start, everything else 
    (e.g. intergreens, end requests) are handled by the groups 

"""
# Copyright 2022 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

#from transitions.extensions import GraphMachine as Machine
from transitions import Machine as Machine
from confread import GlobalConf # For testing
import pandas as pd

from signal_group import SignalGroup
from signal_group import value_is_number # Should be in utils unit or something
from timer import Timer
from stats import StatLogger
from detector import Detector, ExtDetector, GrpDetector, e3Detector
from extender import Extender, StaticExtender, e3Extender
from lane import Lane
import sys
import json

MAX_SIM_TIME = 200 # seconds
#DEFAULT_CONF_FILE = "testmodel/nats_controller.json" # Only for testiruns
DEFAULT_CONF_FILE = "../models/JS270_TBP/JS270TBPIDE2M2_flowmed.json"
CACHE_MODEL_FILE = "../cache/model.json" # This is for storing changes made with UI

def main():
    """
        For testing, runs a simulation
        Params from command line (seel --help for details)
    """

    print("tst")
    sys_cnf = GlobalConf(filename=DEFAULT_CONF_FILE).cnf
    controller_cnf = sys_cnf['controller']
    
    timer_conf = sys_cnf['timer']
    system_timer = Timer(timer_conf)


    controller = PhaseRingController(controller_cnf, system_timer)
    #datafreame = controller.get_group_params_as_df()
    #print(controller.get_group_params_as_df())
    #print("****")
    #print(controller.get_intergreens_as_df())
    #print("Intergreens from conf:")
    #print(controller.intergreens)
    #print("Intergreens from groups:")
    #print(controller.get_intergreens_as_df())
    #print("****")
    #print(controller.get_phases_as_df())
    #print(controller.get_lane_params_as_df())
    #print(controller.phase_ring)
    #print(controller.get_phases())


    #print(json.dumps(controller.get_conf_as_dict(), indent=4))

    # controller.simulate_operation()



class SimplePhase():
    def __init__(self, name, groups):
        self.groups = groups
        self.name = name

    def __str__(self):
        ret = "PH:" + str(self.name)
        return ret
    

# Conditional functions for operating the main controller
    # These will dictate state transfers
    #

    def phase_has_started(self):
        """returns true if any group in phase has green on"""
        Phase_started = False
        for grp in self.groups:
            if grp.is_starting():
                Phase_started = True
        if Phase_started: 
            for grp in self.groups:
                grp.phase_started_at = grp.system_timer.seconds                
        return Phase_started # No greens found

    def green_has_started(self):
        """returns true if any group in phase has green on"""
        for grp in self.groups:
            if grp.is_in_min_green():
                return True
        return False # No greens found

    def one_min_green_has_ended(self):
        """returns True if one group is past min green in this phase"""
        #print("**** one_min_green_has_ended")
        for grp in self.groups:
            if grp.is_not_in_min_green():            
                print('Min Green Ended: ', grp.group_name)
                return True
        return False # No greens found
    
    def all_min_greens_have_ended(self):
        """returns True if all groups are past min green in this phase"""
        MinGreensEnded = True
        for grp in self.groups:
            if grp.is_in_min_green():            
                return False
        print("All min greens have ended")
        return MinGreensEnded  
    
    def phase_min_time_reached(self):
        """returns True if all groups are past min green in this phase"""
        MinTimeReached = False
        for grp in self.groups:
            phasemin = grp.phase_min_time_reached()  
            if phasemin > 0: 
                print("Phase min time reached: ", grp.group_name, " , ", round(phasemin,1))         
                return True    
        return MinTimeReached  

    def phase_has_a_request(self):
        """True if any group is requesting green"""
        for grp in self.groups:
            if grp.has_green_request():
                return True
        return False

# Control functions to groups
    #
    def set_permit_greens(self, do_permit=True):
        """
            Gives green permissions to all groups in this phase
            Called when the next phase is selected 
            (and groups in there are allowed to start)
        """
        for grp in self.groups:
            grp.permit_green = do_permit

    def phase_has_a_requested_group_wihthout_conflicts(self):
        """True if any group is requesting green and there is no conflicting group requesting green"""
        non_conflicting_group_found = True
        for grp in self.groups:
            if grp.has_green_request() and grp.all_conflicts_red():
                non_conflicting_group_found = True
        return non_conflicting_group_found

    # DBIK231128 New function for giving individual green permission to a signal group
    def set_signalgroup_green_permissions(self, do_permit=True):
        """True if any group is requesting green and there is no conflicting active green signals"""
        green_permission_given = False
        for grp in self.groups:
            if grp.has_green_request() and grp.conflicting_active_green_passed():
                grp.permit_green = do_permit
                grp.remove_conflicting_green_permissions() # DBIK231204 removes any previous green permission in conflict
                # green_permission_given = True
        
        # DBIK231129 If one group is vien green permission, then other groups in the phase can be given, too
        if green_permission_given: 
            for grp in self.groups:
                if grp.conflicting_active_green_passed():
                    grp.permit_green = do_permit
                    grp.remove_conflicting_green_permissions() # DBIK231204 removes any previous green permission in conflict
        
         # DBIK231211 removes green permission from pedestrian groups if a yielding vehicle group has started    
        for grp in self.groups:
            if grp.permit_green and grp.request_green and grp.group_name == 'group15':
                for dgrp in grp.disabling_groups:
                    if dgrp.is_starting() or dgrp.group_green_or_amber():
                        # if grp.request_green == True:
                            # print('Disable green permit of: ', grp.group_name,' by group: ', dgrp.group_name) # DBIK20240926 Send the message once only
                        grp.request_green = False  # DBIK231212 removes green request from pedestrian group if a yielding vehicle group has started
                        grp.permit_green = False    
                                               

        return green_permission_given
    
    # DBIK230908 New function for detectecting if active greens have ended
    def all_active_greens_have_ended(self):
        """returns true if no group in current phase is extending """
        for grp in self.groups:
            if not(grp.active_green_passed()):
                return False
        return True # No greens found

###############################################################################################################

class PhaseRingController:
    """PhaseRingController
        This is a controller with flexible 'phaseless' operation
        The phase ring defines only a round robin preference for the
        groups to be started. Main tool for operation is the conflict matrix
        and independend operation of groups
    """

    # conf is a dictionary read from conf file
    # Note: currently there is not much  sanity check for the
    # Params, there should be
    def __init__(self, conf, timer):
        if "name" in conf:
            self.name = conf['name']
        else:
            self.name = "unnamed"

        #print("Initializing a controller:", self.name)

        # This timer will be relayed to all the objects
        # i.e. groups and detectors
        self.timer = timer
        # Stat logger?

        #phase_ring will be tuple of tuples
        new_phases = []
        for conf_phase in conf['phases']:
            new_phases.append(tuple(conf_phase))
        phase_ring = tuple(new_phases) #immutable from now on

        #intergreens will be tuple of tuples
        new_intergreens = []
        for from_group in conf['intergreens']:
            new_intergreens.append(tuple(from_group))
        intergreens = tuple(new_intergreens)

        # We init the lanes
        self.lanes = []
        if 'lanes' in conf:
            for lane_id, lane_conf in conf['lanes'].items():
                lane_conf['id'] = lane_id
                lane = Lane(lane_conf)
                self.lanes.append(lane)


        # We map these groups to main phases (rows in phase ring)
        self.group_list = conf['group_list']
        if not len(phase_ring[0]) == len(self.group_list):
            print("phases and groups not matching")
            sys.exit()

        groups = []
        controller_index = 0
        for group_id in self.group_list:
            controller_index += 1 # Note: indexing starts from 1
            conf_vals = conf['signal_groups'][group_id]
            new_group = SignalGroup(self.timer, group_id, conf_vals, controller_index=controller_index)
            #new_group.stat_logger = self.stat_logger
            groups.append(new_group)
        self.groups = tuple(groups)

        self.set_conflict_groups(intergreens) # DBIK240807 Moved before extender creation

        # By default sumo ouptuts are the same as group list
        # i.e. for each group there is one output and the order
        # is the same as group order. This can be overridden with
        # function set_sumo_outputs
        self.sumo_outputs = self.groups

        #setup manin phases
        self.set_phase_ring(phase_ring)


        # We assign the detectors: extensiton detectors
        # ext_dets are later assigned to extenders
        # Requests are handled in this class
        self.req_dets = []
        self.ext_dets = []
        self.ext_groups = []
        self.extenders = []
        self.e3detectors = []
        self.e3extenders = []

        det_cnf = conf['detectors']
        # Note: this is imitted if the unit is used as an web interface template, might find a better way
        if self.timer:
            time_step = self.timer.time_step # should be realayed as timer?
        else:
            time_step = 0.1

        

        for det in det_cnf:

            if det_cnf[det]['type'] == 'request':
                new_det = Detector(self.timer, det, det_cnf[det])
                new_det.set_request_groups(self.groups) # Into init?
                self.req_dets.append(new_det) # Note: not used at the moment

            if det_cnf[det]['type'] == 'extender':
                new_det = ExtDetector(self.timer, det, det_cnf[det])
                self.ext_dets.append(new_det) # these are for detector extenders

            if det_cnf[det]['type'] == 'groupext':
                new_det = GrpDetector(self.timer, det, det_cnf[det])
                # new_det.group = self.get_signal_group_object(new_det.group_name)
                #new_det.owngroup_name = new_det.group_name  # DBIK231216
                new_det.extgroup = self.get_signal_group_object(new_det.extgroup_name)
                self.ext_groups.append(new_det) # these are for group extenders
                     
            if det_cnf[det]['type'] == 'e3detector':  # DBIK240731 new detector type (e3) and extender types (e3)
                new_det = e3Detector(self.timer, det, det_cnf[det]) # create e3 detector
                self.e3detectors.append(new_det) # Add new detector type (e3)

            new_det.owngroup_obj = self.get_signal_group_object(new_det.owngroup_name)

        # DBIK240802 Only create an extender for a signal group, if there are extending detectors of its own
        for group in self.groups:
            dets = []
            e3dets = []
            for det in self.ext_dets:               
                if det.owngroup_name == group.group_name:
                    dets.append(det)
            if (dets != []):   
                new_ext = Extender(self.timer, group, dets, self.ext_groups, e3dets)
                self.extenders.append(new_ext)
        
        # DBIK240803 Create e3extenders based on e3detectors
        for group in self.groups:
            dets = []
            qdets = []
            e3dets = []
            for e3det in self.e3detectors:               
                dgr = e3det.owngroup_name
                grn = group.group_name
                if e3det.owngroup_name == group.group_name:
                    e3dets.append(e3det)
            if (e3dets != []):   
                new_ext = e3Extender(self.timer, group, dets, qdets, e3dets)
                self.e3extenders.append(new_ext)

        DB = 2
        print('---------------------------------------------------------------')
        print('Requesting e1 detecotrs set:  ')
        print(self.req_dets)
        print('Extending e1 detectors set:  ')
        print(self.ext_dets)
        print('Extending signal groups set:  ')
        print(self.ext_groups)
        print('e1 Extenders set: ')
        print(self.extenders)
        print('e3 Extenders set: ')
        print(self.e3extenders)
        print('---------------------------------------------------------------')

        self.print_controller_params()

        self.set_delay_groups() # DBIK231208  Start delays configuration

        self.set_side_requests() # DBIK231214 Side requests configuration

        print('____')

        self.status = 'Scan'
        self.prev_phase_order_str = ''


    def tick(self):
        """This is the clocking function moving the group states and system timer
        And in effect the phasing (timing depenmds on group operations)"""

        # extension is based on this
        for det in self.ext_dets:
            det.tick()  # testing git branch 3

        # Sets the detector requests, if reset in previus cycle
        for det in self.req_dets:
            det.tick()
            
        # DBIK240821 Updates the Multi-Entry/Exit (e3) Detectors
        for det in self.e3detectors:
            det.tick()

        for grp in self.groups:
            grp.prev_state = grp.state # DBIK20231013 Save the previous states 

        for grp in self.groups:
            if grp.extender: 
                grp.extender.tick() # DBIK230331 The extender update moved here
            if grp.e3extender:     
                grp.e3extender.tick() # DBIK240803 The e3extender update added
            if grp.group_name == 'group3':
               DB = 1
            grp.tick()
           
    
        # self.transfer_states() 
        self.update_states2()  # No more using the state machine
        
        # self.timer.tick() DBIK230713 Commented out (double timer update per cycle)

        
        
        # All after this is run conditionally


    def find_the_next_main_phase(self):
        """Returns the next phase based pn ring and requests"""

        # we find the list of next phases in ring
        # Could be fine beforehandf with linked list (for example)
        mph_before = []
        mph_after = []
        mph_current = []
        current_found = False
        for mph in self.main_phases:
            #print("***", mph, " current:", self.current_main_phase)
            if self.current_main_phase==mph:
                current_found = True
                mph_current.append(mph)
                #print("       found")
                continue
            if not current_found:
                mph_before.append(mph)
            else:
                mph_after.append(mph)

        # phase_order = mph_after + mph_before
        
        phase_order = mph_current + mph_after + mph_before # DBIK241002 Current phase first in the phase order
        # phase_order = mph_after + mph_before + mph_current # DBIK241002 Current phase last in the phase order

        phase_order_str = 'phase order: '
        for mps in phase_order:
            phase_order_str = phase_order_str + str(mps) + ' '

        nextPH = None
        for mph in phase_order:
            if mph.phase_has_a_request():
                nextPH = mph
                break
            
        phase_order_str = phase_order_str + ', curPH: ' + str(self.current_main_phase) + ', nextPH: ' + str(nextPH)

        if phase_order_str != self.prev_phase_order_str:
            print(phase_order_str)
            self.prev_phase_order_str = phase_order_str

        return nextPH # No requests -> No main phase
  
    def update_states2(self):
        """  Scans for next phase and sets controller state transfer """
        
        if self.status == 'Scan':
            self.next_main_phase = self.find_the_next_main_phase()
            if self.next_main_phase:
                self.next_main_phase.set_signalgroup_green_permissions(do_permit=True)
        
        for grp in self.groups:
                if grp.is_in_min_green():
                    grp.permit_green = False
                    if grp.own_request_level > 2: 
                        grp.own_request_level = 2   #DBIK241030 Reset priority request
                        for confgrp in grp.conflicting_groups:
                            confgrp['group'].other_request_level = 2  #DBIK241107 Reset conflict group priority request
                
        if self.next_main_phase:
            if self.next_main_phase.phase_has_started(): 
                self.current_main_phase = self.next_main_phase
                self.next_main_phase = None
                print("NEW PHASE STARTED:", self.current_main_phase)
                self.status = 'Hold'
        
        if self.status == 'Hold':
            if self.current_main_phase:
                self.current_main_phase.set_signalgroup_green_permissions(do_permit=True)
                if self.current_main_phase.all_min_greens_have_ended():  
                # if self.current_main_phase.phase_min_time_reached():  #DBIK 20240926 One group reached the phase min  
                        self.status = 'Scan'
             


    def update_states(self):
        """  Scans for next phase and sets controller state transfer """
        
        if self.status == 'Scan':
            self.next_main_phase = self.find_the_next_main_phase()
            if self.next_main_phase:
                self.next_main_phase.set_signalgroup_green_permissions(do_permit=True)
        
        MultiPrio = False
        if MultiPrio:
            for grp in self.groups:
                    if grp.min_green_start: # DBIK241107 State shift, under testing 
                        grp.permit_green = False
                        grp.own_request_level = 2   #DBIK241030 Reset priority request
                        for confgrp in grp.conflicting_groups:
                            OtherPrioReq = 2
                            for conf2grp in confgrp.conflicting_groups: # DBIK241119 Check if there are other active priority requests
                                if conf2grp.own_request_level > 2:
                                    OtherPrioReq = conf2grp.own_request_level
                            confgrp['group'].other_request_level = OtherPrioReq  #DBIK241107 Reset conflict group priority request
        else:
            for grp in self.groups:
                if grp.min_green_start: # DBIK241107 State shift, under testing 
                    grp.permit_green = False
                    grp.own_request_level = 2   #DBIK241030 Reset priority request
                    for confgrp in grp.conflicting_groups:
                        confgrp['group'].other_request_level = 2  #DBIK241107 Reset conflict group priority request
          
            


        if self.next_main_phase:
            if self.next_main_phase.phase_has_started(): 
                self.current_main_phase = self.next_main_phase
                self.next_main_phase = None
                print("NEW PHASE STARTED:", self.current_main_phase)
                self.status = 'Hold'
        
        if self.status == 'Hold':
            if self.current_main_phase:
                self.current_main_phase.set_signalgroup_green_permissions(do_permit=True)
                if self.current_main_phase.all_min_greens_have_ended():  
                # if self.current_main_phase.phase_min_time_reached():  #DBIK 20240926 One group reached the phase min  
                        self.status = 'Scan'
             

    def get_control_status(self):

        """Returns status info (time, phase, group states, requests)"""

        maxstr = 25
        # ExtOut = 'group'
        ExtOut = 'group'
        DetOut = 'reqprio'
        PermOut = 'perm_'
        CutOut ='cut_'
        CutOut ='prio2'

        # e3Out  = 'e3vehCnt'
        e3Out  = 'e3confCnt'
        e3Out  = 'e3crit2'

        sigstat = str(self.get_grp_states())

        sig = ''
        col = 0
        for i in range(len(sigstat)):
            if col % 5 == 0:
                sig += ' '
            col += 1
            sig += sigstat[i] 

        # controller_stat = str(self.timer.steps) + ' ' + sigstat[0:maxstr]
        controller_stat = sig[0:maxstr]  # DBIK230918 remove time stamp
        
        #cur_phase = self.get_state(self.state)
        #sub_state = cur_phase.submachine.state
        cur_phase = str(self.current_main_phase)
        nxt_phase = str(self.next_main_phase)  # DBIK: New ouput to status row 
        
        req = '' 
        loop_stat = ""
        det_stat = ""
        ext_stat = ""
        prm_stat = ""
        cut_stat = ""
        qdet_stat = ""
        e3det_stat = ""
        e3ext_stat = ""

        col = 0
        if DetOut=='loop':
            for det in self.req_dets:
                if det.loop_on:
                    loop_stat += '1'
                else:
                    loop_stat += '0'
            controller_stat += " LOOP:" + loop_stat[0:30] + ' '
        
        elif DetOut=='req':
            for grp in self.groups:
                
                if col % 5 == 0:
                   req += ' '
                col += 1
                   
                if grp.request_green:
                    req += '1'
                else:
                    req += '0'
            controller_stat += " REQ:" + req[0:maxstr] + ' '
        
        elif DetOut=='reqprio':
            for grp in self.groups:
                
                if col % 5 == 0:
                   req += ' '
                col += 1
                   
                if grp.request_green:
                    req += str(grp.own_request_level)
                else:
                    req += '0'
            controller_stat += " REQ:" + req[0:maxstr] + ' '
        
        col = 0
        if ExtOut=='group':
            for grp in self.groups:
                if col % 5 == 0:
                   ext_stat += ' '
                col += 1
                if grp.extender or grp.e3extender:
                    if grp.extender:
                        if grp.extender.extend and grp.group_on:
                            ext_stat += "1"
                        else:
                            ext_stat += "0"
                    if grp.e3extender:
                        if grp.e3extender.extend and grp.group_on:
                            ext_stat += "2"
                        else:
                            ext_stat += "0"                  
                else: ext_stat += "X"
            controller_stat += " EXT:" + ext_stat[0:maxstr] + ' '
        else:
            for det in self.ext_dets:
                if det.is_extending():
                   det_stat += "1"
                else:
                 det_stat += "0"
            controller_stat += " DEXT: " + det_stat[0:maxstr] + ' '
            for gdet in self.ext_groups:
                if gdet.is_extending():
                   qdet_stat += "1"
                else:
                 qdet_stat += "0"
            controller_stat += " QEXT: " + qdet_stat[0:maxstr] + ' '

        col = 0
        if PermOut=='perm':
            for grp in self.groups:
                if col % 5 == 0:
                   prm_stat += ' '
                col += 1
                if grp.permit_green:
                    prm_stat += '1'
                else:
                    prm_stat += '0'
            controller_stat += " PERM:" + prm_stat[0:maxstr] + ' '

        col = 0
        if CutOut=='cut':
            for grp in self.groups:
                if col % 5 == 0:
                   cut_stat += ' '
                col += 1
                if grp.end_conflicting_greens_status(): # and grp.group_on():
                    cut_stat += '1'
                else:
                    cut_stat += '0'
            controller_stat += " CUT:" + cut_stat[0:maxstr] + ' '

        col = 0
        if CutOut=='prio1':            
            for grp in self.groups:
                if col % 5 == 0:
                   cut_stat += ' '
                col += 1
                if grp.end_conflicting_greens_status() and grp.group_on():
                    cut_stat += str(grp.other_request_level)
                else:
                    cut_stat += '0'
            controller_stat += " PRI:" + cut_stat[0:maxstr] + ' '

        col = 0
        if CutOut=='prio2':
            for grp in self.groups: 
                if col % 5 == 0:
                   cut_stat += ' '
                col += 1               
                cut_stat += str(grp.other_request_level)
            controller_stat += " PRI:" + cut_stat[0:maxstr] + ' '


        controller_stat += '(cur:{}, next:{})'.format(cur_phase, nxt_phase)

        if self.status == 'Scan':
            controller_stat += ' S'
        if self.status == 'Hold':
            controller_stat += ' H'

        if e3Out  == 'e3confCnt':
            for e3det in self.e3detectors:
                val = e3det.veh_count()
                e3det_stat += str(val) + ','
            controller_stat += " e3veh: " + e3det_stat[0:maxstr] + ' '

        if e3Out  == 'e3confCnt':
            for e3ext in self.e3extenders:
                val = e3ext.conf_sum
                e3ext_stat += str(val) + ','
            controller_stat += " e3conf: " + e3ext_stat[0:maxstr] + ' '

        if e3Out  == 'e3crit':
            for e3ext in self.e3extenders:
                if e3ext.extend:
                    val1 = e3ext.vehcount
                    val2 = e3ext.conf_sum
                    if val2 > 0:
                        val = round(val1/val2, 2)
                    else: 
                        val = -1
                    e3ext_stat += str(val) + ','
            controller_stat += " e3rel: " + e3ext_stat + ' '

        grpno =0
        if e3Out  == 'e3crit2':
            for grp in self.groups:
                grpno += 1
                if grp.e3extender:                   
                    if grp.get_grp_state() in ['5']:
                        val1 = grp.e3extender.vehcount
                        val2 = grp.e3extender.conf_sum
                        val3 = round(grp.e3extender.threshold,1)
                        if val2 > 0:
                            val = round(val1/val2,1)
                        else: 
                            val = 10.0
                        e3ext_stat += str(grpno) + ':'
                        e3ext_stat += str(val)
                        if val > val3:
                            ch = '>'
                        else:
                            ch = '<'
                        e3ext_stat += ch
                        e3ext_stat += str(val3) + '|'

            controller_stat += " E3: " + e3ext_stat + ' '

        return controller_stat

    def start_a_new_phase(self):
        self.current_main_phase = self.next_main_phase
        self.next_main_phase = None
        print("NEW PHASE STARTED:", self.current_main_phase)
       
    def next_phase_selected(self):
        print("NEXT PHASE FIXED: ", self.next_main_phase)
    

    #
    # State transfer conditions
    #

    def curr_phase_a_min_green_ended(self):
        """
            Returns true if any min green has passed
            by any of the groups in _current_ phase
        """
        
        if self.current_main_phase:
            return self.current_main_phase.one_min_green_has_ended()
        
        return False

    def next_phase_a_green_started(self):
        """
            Returns true if a green has been started 
            by any of the groups in _next_ phase
        """
        if self.next_main_phase:
            # return self.next_main_phase.green_has_started()
            return self.next_main_phase.green_has_started() # DBIK231129 Phase starts if any group at IG or Amber
        
        return False
    
    def curr_phase_active_greens_ended(self):
        """
            Returns true if there is no active green extension 
            by any of the groups in _current_ phase
        """        
        if self.current_main_phase:
            return self.current_main_phase.all_active_greens_have_ended()
        
        return False


    #   
    # Controller operation
    # 
    #
    # Init Functions
    # 

    def set_conflict_groups(self, intergreens):
        """
            We set the conflicting groups
            These are based on intergreen matrix
        """
        # clear the previous conflicts
        for grp in self.groups:
            grp.conflicting_groups = []
            grp.non_conflicting_groups = []


        # FIXME: the naming is stupid, intergreens is used in the loop and means different thing
        for to_grp, intergreens in zip(self.groups, intergreens):
            # If there is integreen time from a group to this group (to_group)
            # We add this conflict to group
            for from_grp, intergreen in zip(self.groups, intergreens):
                if not intergreen==0.0:
                    to_grp.add_conflicting_group(from_grp, delay=intergreen)
                else: 
                    to_grp.add_non_conflicting_group(from_grp, delay=intergreen) # DBIK 230915 add to the list of non conflicting groups
        


    def set_side_requests(self):
        """ Set groups that will be requested, if this group gets request"""
        print('Find side requests: ')
        for grp in self.groups: 
            if "side_requests" in grp.grp_conf:  
                sidereqs = grp.grp_conf['side_requests']
                # print('Group:', grp.group_name, ', Side requests list: ', sidereqs)
                if sidereqs: 
                    for sgrp_name in sidereqs:
                        sgrp = self.get_signal_group_object(sgrp_name)
                        grp.side_requests.append(sgrp)        
                    print('Group:', grp.group_name, ', Side requests: ', grp.side_requests)


    def set_delay_groups(self):
        """ Set groups that need to be waited"""
        print('Find delay groups: ')
        for grp in self.groups: 
            dd = self.get_delay_dictionary(grp)
            delgroups = self.set_starting_delays(grp,dd)
            if delgroups: 
                for dgrp in delgroups:
                    grp.delaying_groups.append(dgrp)
                    dgrp.disabling_groups.append(grp)
                print('Group:', grp.group_name, ', Delay groups: ', grp.delaying_groups, 'Disable groups: ', dgrp.disabling_groups)
        
    def get_delay_dictionary(self, grp):
        deldict = {}  
        if "delaying_groups" in grp.grp_conf:       
            deldict = grp.grp_conf["delaying_groups"]
            # print('Group', grp.group_name, ' delgroups: ', deldict)
            return deldict
        return None 
            
    def set_starting_delays(self,grp,deldict):
        delgroups = []    
        if not(deldict):
            return None   
        for delgroupname in deldict:
            delgroup = self.get_signal_group_object(delgroupname)
            delgroups.append(delgroup)
        # print('Grp:', grp.group_name, ' Delay groups: ', delgroups)
        return delgroups
                    
    def get_signal_group_object(self,grpname):
        """Returns signal group object based on name"""
        for grp in self.groups:
            if grp.group_name == grpname:
                return grp
        return None
                
        
    def set_phase_ring(self, phase_ring):
        "Defines the phase ring based on tuple of tuples (ie phase ring matrix)"
        self.main_phases = []
        ph_index = 1
        for row in phase_ring:
            #print(row)
            groups_in_mp = []
            for grp, ph_stat in zip(self.groups, row):
                if ph_stat==1:
                    groups_in_mp.append(grp)
            new_main_phase = SimplePhase(ph_index, groups_in_mp)
            print("Phase: ",ph_index," ",groups_in_mp)
            ph_index += 1
            self.main_phases.append(new_main_phase)
        self.current_main_phase = None # we are not in any main phase
        self.next_main_phase = None # Next scheduled main phase

    # This is for mapping one controller for many sumo signalheads
    def set_sumo_outputs(self, grouplist):
        """Overrides sumo outputlist defined in init"""
        groups = []
        for grp_name in grouplist:
            for grp in self.groups:
                if grp.group_name == grp_name:
                    print("FOUND:", grp_name)
                    groups.append(grp)
        if len(groups)==len(grouplist):
            self.sumo_outputs = groups
        else:
            print("WARNING: some sumo groups not found")

    #
    # Conf functions
    # 

    def get_conf_as_dict(self):
        "Returns controller conf file as dictionary"
        conf = {}
        conf['controller'] = {}
        conf['controller']['name'] = "test"  #self.name
    
        # Signal groups
        conf['controller']['signal_groups'] = {}
        for group in self.groups:
            conf['controller']['signal_groups'][group.group_name] = group.get_params()
    
        # Detectors
        conf['controller']['detectors'] = {}
        for det in self.req_dets:
            conf['controller']['detectors'][det.name] = det.get_params()
        for det in self.ext_dets:
            conf['controller']['detectors'][det.name] = det.get_params()
        for det in self.ext_groups:
            conf['controller']['detectors'][det.name] = det.get_params()

        # Lanes
        conf['controller']['lanes'] = {}
        for lane in self.lanes:
            conf['controller']['lanes'][lane.id] = lane.get_params()
        
        # group lista
        conf['controller']['group_list'] = self.group_list

        # phases
        conf['controller']['phases'] = []
        for phase in self.get_phases():
            conf['controller']['phases'].append(list(phase))


        # Intergreens
        ig_tuples = self.get_intergreens()
        intergreens = []
        for from_group in ig_tuples:
            intergreens.append(list(from_group))
        conf['controller']['intergreens'] = intergreens
        return conf


    def process_new_conf(self, new_conf):
        "This is for processing new conf-coming from the UI as a dictionary"
        
        if not 'controller' in new_conf:
            return "No controller in conf"
        
        
        # Signal groups
        if not 'signal_groups' in new_conf['controller']:
            return "No signal_groups in conf"
        for conf_group in new_conf['controller']['signal_groups']:
            for group in self.groups:
                if group.group_name == conf_group:
                    group.set_params(new_conf['controller']['signal_groups'][conf_group])
        
        # Intergreens, Note: this has not been tested in practice
        if not 'intergreens' in new_conf['controller']:
            return "No intergreens in conf"
        new_intergreens = []
        for from_group in new_conf['controller']['intergreens']:
            new_intergreens.append(tuple(from_group))
        intergreens = tuple(new_intergreens)
        self.set_conflict_groups(intergreens)

        
        return "Ok"


    def save_conf(self, filename=CACHE_MODEL_FILE):
        "Saves the controller conf to a file"
        conf = self.get_conf_as_dict()
        with open(filename, 'w') as outfile:
            json.dump(conf, outfile, indent=4)

    
    def read_conf(self, filename=CACHE_MODEL_FILE):
        "Reads the controller conf from a file"
        with open(filename) as json_file:
            conf = json.load(json_file)
        self.process_new_conf(conf)
        return conf

    #
    # Print and export functions
    #

    def print_controller_params(self):
        "Prints basic controller set up"
        print("Controller:", self.name)
        print("\nPHASE RING")
        for phase in self.get_phases():
            print(phase)

        # Maybe at group ids here?
        print("\nINTERGREENS")
        for to_group in self.get_intergreens():
            print(to_group)
        
        print("\nGROUPS")
        print(self.groups)

        # for grp in self.groups:
        #     print('Grp: ', grp.group_name, 'Conf: ', grp.grp_conf)
        
        print("\nREQUEST DETS")
        print(self.req_dets)

        print("\nEXTENDING DETS")
        print(self.ext_dets)

        print("\nEXTENDING GROUPS")
        print(self.ext_groups)

        print("\nEXTENDERS")
        print(self.extenders)

        print("\nCONFLICT MATRIX")
        conflicts = self.get_conflict_matrix()
        for conflict_row in conflicts:
            print(conflict_row)

        print("\nMAIN PHASES")
        for mp in self.main_phases:
            print(mp)
        print(self.main_phases)  # DBIK 20231010 


        print("___")


    def get_conflict_matrix(self):
        """Retunrs the conflict matrix as tuple"""
        matrix = []
        for y in self.groups:
            line = []
            for x in self.groups:
                if y.group_in_conflict(x):
                    line.append(1)
                else:
                    line.append(0)
            matrix.append(tuple(line))
        return tuple(matrix)


    def simulate_operation(self, max_ext=True):
        """
            Runs the simulation of the operation without any inputs
            This is used for testing and will end after constant
            MAX_SIM_TIME
        """

        static_extender = StaticExtender(max_ext)


        print('Simulate the cycle')
        for grp in self.groups:
            #grp.request_green = True
            grp.extender = static_extender


        #self.stat_logger.reset()
        self.timer.reset()


        
        stop_sim = False
        while not stop_sim:
            self.tick()
            print(self.get_grp_states(), "", self.timer)
            if self.timer.seconds >= MAX_SIM_TIME:
                stop_sim = True

        print('simulated:', self.timer)


    def get_intergreens(self):
        "Returns the intergreen matrix as a tuple"
        intergreens = []
        group_count = len(self.groups)
        for group in self.groups:
                blocking = [0.0] * group_count # by default, no intergreens
                for conflicting in group.conflicting_groups:
                    index = self.groups.index(conflicting['group'])
                    blocking[index] = conflicting['delay']
                intergreens. append(tuple(blocking))

        return tuple(intergreens)
    
    def get_phases(self):
        "Returns the phase ring as a tuple"
        phases = []
        for phase in self.main_phases:
            phase_row = []
            for group in self.groups:
                if group in phase.groups:
                    phase_row.append(1)
                else:
                    phase_row.append(0)
            phases.append(tuple(phase_row))
        return tuple(phases)


   
    #
    # Output functions
    #


    def get_status_as_dict(self):
        status = {}
        status['step_count'] = self.timer.steps
        status['group_states'] = self.get_grp_states()
        status['current_phase'] = str(self.current_main_phase)
        status['next_phase'] = str(self.next_main_phase)
        ext_stat = ""
        for grp in self.groups:
            if grp.extender:
                if grp.extender.extend:
                    ext_stat += "1"
                else:
                    ext_stat += "0"
            else:
                ext_stat += "N"
        status['extender_states'] = ext_stat
        req_stat = ""
        for grp in self.groups:
            if grp.request_green:
                req_stat += "1"
            else:
                req_stat += "0"
        status['request_states'] = req_stat

        return status
    

    def get_grp_states(self):
        """Returns group statuses as string in traditional format"""
        sstats = ''

        for grp in self.groups:
            sstats += grp.get_grp_state()

        return sstats


    def get_sumo_states(self):
        """Returns group statuses as string Sumo-format"""
        sstats = ''

        for grp in self.sumo_outputs:
            sstats += grp.get_sumo_state()

        return sstats

    # 
    # UI functions
    #


    def get_group_params_as_df(self):
        'Returns group params as pandas dataframe'
        all_groups = {}
        for group in self.groups:
            #print("Name", group.name, "Params:",  group.get_params())
            params = group.get_params()
            all_groups[group.name] = params
        print(all_groups) 
        df = pd.DataFrame(all_groups)
        
        #print(df)
        df = df.transpose()
        #df = df.reset_index()
        #print(df)
        cols = df.columns.tolist()
        cols.pop(cols.index('name'))
        cols = ["name"] + cols
        df = df.reindex(columns=cols)
        #print(cols)
        return df

    def get_lane_params_as_df(self):
        """Returns lane params as pandas dataframe"""
        all_lanes = {}
        
        if not self.lanes:
            return pd.DataFrame(all_lanes) # If lanes are not defined, return empty dataframe
        
        for lane in self.lanes:
            #print("Name", group.name, "Params:",  group.get_params())
            params = lane.get_params()
            #We remove the coodintaes, since we don't want to show them
            if 'coordinates' in params:
                #coords = params['coordinates']
                #params['coordinates'] = str(coords)
                params.pop('coordinates')
            # we convert users as string, since we want a simplified UI
            if 'users' in params:
                users = params['users']
                params['users'] = str(users)
            all_lanes[lane.id] = params
        df = pd.DataFrame(all_lanes)
        df = df.transpose()
        cols = df.columns.tolist()
        cols.pop(cols.index('id'))
        #cols = ["id"] + cols    
        df = df.reindex(columns=cols)
        return df
    
    
    def get_intergreens_as_df(self):
        'Returns intergreen matrix as pandas dataframe'
        intergreen_table = {}

        # Note, the matrix order is based on the group list
        for to_grp, intergreens in zip(self.groups, self.get_intergreens()):
            to_name = to_grp.group_name
            new_row = {}
            new_row['Starting group'] = to_name
            for from_grp, intergreen in zip(self.groups, intergreens):
                from_name = from_grp.group_name
                new_row[from_name] = intergreen
            intergreen_table[to_name] = new_row
        
        #return intergreen_table

        df = pd.DataFrame(intergreen_table)
        
        df = df.transpose()
        cols = df.columns.tolist()
        cols.pop(cols.index('Starting group'))
        cols = ['Starting group'] + cols
        df = df.reindex(columns=cols)
        #print(cols)
        return df

    def get_phases_as_df(self):
        "Returns the phase ring as pandas dataframe"
        phase_table = {}
        phase_id = 1
        for phase in self.get_phases():
            new_row = {}
            new_row["Phase"] = phase_id
            for group, val in zip(self.groups, phase):
                new_row[group.group_name] = val
            phase_name = "Phase " + str(phase_id)
            phase_table[phase_name] = new_row
            phase_id += 1
        df = pd.DataFrame(phase_table)
        df = df.transpose()
        cols = df.columns.tolist()
        cols.pop(cols.index('Phase'))
        df = df.reindex(columns=cols)

        return df

    # Fix me
    def get_detector_params_as_df(self):
        'Returns group params as pandas dataframe'
        detectors = {}
        for det in self.ext_dets:
            #print("Name", group.name, "Params:",  group.get_params())
            params = det.get_params()
            detectors[det.name] = params

        #print(cols)
        return None


    # Note: not in use
    def get_intergreens_as_dict(self):
        """Returns intergreen matrix as pandas dataframe"""
        igs = []
        for row_index, row in enumerate(self.get_intergreens()):
            new_dict = {}
            new_dict['index'] = row_index
            for col_index, val in enumerate(row):
                new_dict[col_index] = val
            igs.append(new_dict)
        return igs

    def update_group_params(self, new_params):
        "Receives group params from the UI as list of dictonaries and updates them"
        # Note: now sure how to make sanity check for these
        #print(new_params)
        for new_param in new_params:
            for group in self.groups:
                if group.group_name == new_param['name']:
                    errors = group.set_params(new_param)
                    if  errors:
                        return errors
        return None # No errors


    def update_ig_params(self, new_params):
        "Receives intergreen params from the UI as list of dictonaries and updates them"
        # Note: now sure how to make sanity check for these
        #print(new_params)
        new_intergreens = []
        for row in new_params:
            blocking = []
            ig_values = list(row.values())
            ig_values.pop(0) # remove the index

            for ig_val in ig_values:
                if not value_is_number(ig_val):
                    return "Non-numeric value in intergreen matrix"
                blocking.append(float(ig_val))
            new_intergreens.append(tuple(blocking))
        new_intergreens = tuple(new_intergreens)
        self.set_conflict_groups(new_intergreens)

        return None # No errors

    # Note: this doesn't work yet, we get too mixed up ehen phases are changed midway
    # Likely an all red phase is needed
    def update_phase_params(self, new_params):
        "Receives intergreen params from the UI as list of dictonaries and updates them"
        # Note: now sure how to make sanity check for these
        #print(new_params)
        new_phases = []
        for row in new_params:
            on_groups = list(row.values())
            new_on_groups = []
            for on_group in on_groups:
                if not (on_group==1 or on_group==0 or on_group=="1" or on_group=="0"):
                    return "Only ones and zeroes allowed in phase matrix"
                new_on_groups.append(int(on_group))
            new_phases.append(tuple(new_on_groups))
        new_phases = tuple(new_phases)
        self.set_phase_ring(new_phases)
        return None # No errors



    

if __name__ == "__main__":
    main()

