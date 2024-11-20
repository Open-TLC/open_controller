# -*- coding: utf-8 -*-
"""The signal group module.

This module implements the signal group state machine to be used in the
signal group controller

"""
# Copyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

import time
import math
#from transitions_gui import WebMachine
#from transitions import Machine, State
#from transitions import State
#from transitions.extensions import HierarchicalGraphMachine as Machine
from transitions.extensions import HierarchicalMachine as Machine
from transitions.extensions.nesting import NestedState as State

# Constant minimums in seconds
MINIMUM_GREEN = 10
MINIMUM_RED = 5
AMBER = 4
AMBER_RED = 2

DEFAULT_TIME_STEP = 0.01  # seconds

INSTANT_TRANSFER = True


def value_is_number(input):
    try:
        float(input)
    except ValueError:
        return False
    return True

def main():
    #TESTING
    from timer import Timer
    from confread import GlobalConf

    timer = Timer(0.1)
    sys_cnf = GlobalConf().cnf
    sg = SignalGroup(timer, 'kari', sys_cnf['controller']['signal_groups']['default'])
    #sg = SignalGroup('test')
    try:
        while True:
            time.sleep(DEFAULT_TIME_STEP)
            sg.tick()
            timer.tick() # this has been changed
            print('state:', sg.state)
    except KeyboardInterrupt:  # Ctrl + C will shutdown the machine
        print("Exiting")

def draw_graphs():
    from timer import Timer
    from confread import GlobalConf

    timer = Timer(0.1) # these should have defaults in group?
    sys_cnf = GlobalConf().cnf
    sg = SignalGroup(timer, 'kari', sys_cnf['controller']['signal_groups']['default'])

    #sg = SignalGroup('test')
    sg.title = 'The signal group main loop'
    sg.show_conditions = True
    sg.show_auto_transitions = True
    sg.show_state_attributes = True
    print('Getting the diagram')
    sg.get_graph(show_roi=False).draw('tmp/ring.png', prog='dot')

    exit()
    diagram_no = 0
    try:
        while True:
            name = 'tmp/my_diagram{}.png'.format(diagram_no)
            diagram_no = (diagram_no + 1) % 4
            sg.get_combined_graph(show_roi=True).draw(name, prog='dot')
            sg.tick()
            print('state:', sg.state)
    except KeyboardInterrupt:  # Ctrl + C will shutdown the machine
        print("Exiting")



# We define state machine following:
# red -> red/amber -> green -> amber -> red...
# We also add a "Start" state for init purposes
# There is no way for any other seguence, ever
# NOTE: Possible exception: amber flash?
# Iside those states we have different state machines...
# Thus we define a DFA as:
#  q_0 = Red
#  Q = {Start, Red, AmberRed, Green, Amber}
#  Sigma = {next_state}
#  delta =
#       (Start, next_state)-> Red
#       (Red, next_state)-> AmberRed
#       (AmberRed, next_state)-> Green
#       (Green, next_state)-> Amber
#       (Amber, next_state)-> Red
# Final state: {} (this machine will never finish)
#
#
# DFA: https://en.wikipedia.org/wiki/Deterministic_finite_automaton
#
# NOTE: Should we add Zero transfers?
#       if for exsample no amber light (e.g. pedestrian lights)

class SignalGroup(Machine):
    """Implements Signal Group state machine"""

    def __init__(self, system_timer, name, grp_conf, instant_transfer=INSTANT_TRANSFER, controller_index=None):
        self.group_name = name # Note, "name" conflicts with Machine?
        self.controller_index = controller_index # groups assigned to controller are indexed from 1 upwards
        self.grp_conf = grp_conf
        self.system_timer = system_timer
        self.prev_state = 'Start'

        # If this is false, only one transfer per tick is made
        # This is usefull for debugging
        self.instant_transfer = instant_transfer

        # Control status variables
        self.red_started_at = 0
        self.amber_started_at = 0
        self.green_started_at = -1
        self.phase_started_at = -1
        self.other_group_requests_end_green = False #This is for rest greens
        

        self.conflicting_groups = []
        self.non_conflicting_groups = []
        self.delaying_groups = []
        self.disabling_groups = []
        self.side_requests = []
        
        # External inputs, signals
        self._request_green = False  # external request to go green
        self._permit_green = False  # controller permission to go green
        
        # External objects to be connected later
        self._extender = None # Extender sets this
        self.e3extender = None # DBIK240803 added
        self._stat_logger = None # set outside

        # Substates
        # For fixed we always use the min as time
        self.fixed_amber = FixedTime(self.system_timer, self, min_length=grp_conf['min_amber'])
        self.fixed_amber_red = FixedTime(self.system_timer, self, min_length=grp_conf['min_amber_red'])
        # Should this be dependent on conf?
        self.va_green = VehicleActuated(self.system_timer, self,
                                        min_length=grp_conf['min_green'],
                                        max_length=grp_conf['max_green'],
                                        green_end=grp_conf['green_end']
                                        )
        # Note: should add intergreen as own phase (ie other statemachine here)
        # fixed_red = FixedTime(self.system_timer, self, min_length=grp_conf['min_red'])
        self.group_based_red = GroupBasedRed(self.system_timer, self, min_length=grp_conf['min_red'])


        states = [
            State(name='Start'),
            #State(name='Red', on_enter='start_red'),
            {'name': 'Red', 'on_enter': self.start_red_cb, 'children':self.group_based_red},
            {'name': 'AmberRed', 'children':self.fixed_amber_red},
            {'name': 'Green', 'on_enter': self.start_green_cb, 'children':self.va_green},
            {'name': 'Amber', 'on_enter': self.start_amber_cb, 'children':self.fixed_amber}
            ]
        transitions = [
            {
                'trigger': 'next_state',
                'source': 'Start',
                'dest': 'Red_Init'
            },
            {
                'trigger': 'next_state',
                'source': 'Red_Exit',
                'dest': 'AmberRed_Init'
            },

            {
                'trigger': 'next_state',
                'source': 'AmberRed_Exit',
                'dest': 'Green_Init'
            },
            {
                'trigger': 'next_state',
                'source': 'Green_Exit',
                'dest': 'Amber_Init'
            },

            {
                'trigger': 'next_state',
                'source': 'Amber_Exit',
                'dest': 'Red_Init'
            }
        ]
        initial = 'Start'

        # Note, this deorates this object by passing self...
        Machine.__init__(
            self,
            name=name,
            states=states,
            transitions=transitions,
            initial=initial,
            auto_transitions=False
            )

        self.next_state() # This will trigger the Start->Red

    
    #
    # Init Functions
    #

    # Controller calls these
    def add_conflicting_group(self, group, delay=0):
        """Adds a conflicting group for this group
        Delay is time the conflict blocks green after it is gone to red"""
        conflicting = {
            'group': group,
            'delay': delay
        }
        self.conflicting_groups.append(conflicting)
    
    # Controller calls these
    # DBIK 230915 add to the list of non conflicting groups
    def add_non_conflicting_group(self, group, delay=0):
        """Adds a non conflicting group for this group, Delay time is zero"""
        conflicting = {
            'group': group,
            'delay': delay
        }
        self.non_conflicting_groups.append(conflicting) 
    

    #
    # State machine callbacks
    #

    def start_green_cb(self):
        self.green_started_at = self.system_timer.seconds
        if self.group_name == 'group1':
            print('Veh group: ', self.group_name,' Time of green start', self.system_timer.seconds)
        
    def start_red_cb(self):
        # Note: this is imitted if the unit is used as an web interface template, might find a better way
        if self.system_timer:
            self.red_started_at = self.system_timer.seconds

    def start_amber_cb(self):
        self.amber_started_at = self.system_timer.seconds
        

    #
    # Print and export data functions
    #


    # Used eg for printing conflict matrix
    def group_in_conflict(self, group):
        """Returns true if this group conflicts with a given group"""
        for c_group in self.conflicting_groups:
            if c_group['group'] == group:
                return True
        return False


    def __repr__(self):
        ret = '<Group {}>'.format(self.group_name)
        return ret


    def __str__(self):
        ret = '<Group {}>\n'.format(self.group_name)
        # ret += '  Conflicting: {}'.format(self.conflicting_groups)
        ret += '  Delaying: {}'.format(self.delaying_groups)  # DBIK231209
        return ret

    def get_grp_state(self):
        """Returns status (char) of the group in 'traditional' format"""
        grp_statuses = {
            'Red_MinimumTime': 'a',
            'Red_CanEnd': 'b',
            'Red_ForceGreen': 'f',
            'Red_WaitIntergreen': 'g',
            'AmberRed_MinimumTime': '0',
            'Green_MinimumTime': '1',
            'Green_Extending': '5',
            'Green_RemainGreen': '4',
            'Amber_MinimumTime': '>'     
        }
        status = grp_statuses.get(self.state, '*')

        # Should be own state
        if status in ['b'] and self.request_green:
            status = 'c'
        if status in ['b'] and self.grp_conf['request_type'] == 'fixed':
            status = 'C' # FIX ME
        if status in ['b'] and self.permit_green:
            status = 'e' 

        return status



    def get_sumo_state(self):
        """Returns status in sumo format (char)"""
        # Note: this is not correct mapping

        # Note: assumed the state names to be separated by _
        parent_state = self.state.split('_')[0]

        sumo_statuses = {
            'Red': 'r',
            'Green': 'g',
            'Amber': 'y',
            'AmberRed': 'u'
        }
        return sumo_statuses[parent_state]


    def get_params(self):
        """Returns parameters of the group as dict"""
        params = self.grp_conf
        params["name"] = self.group_name
        # Debug: not implemented inui
        if "delaying_groups" in params:
            #params["delaying_groups"] = "Test" #str(params["delaying_groups"])
            del params["delaying_groups"]
        return params

    def set_params(self, params):
        """Sets parameters of the group from dict"""
        errors = self.any_errors_in_param_input(params)
        if not errors:
            self.grp_conf = params
            # We have to set the params in the submachines
            self.fixed_amber.min_length = float(params['min_amber'])
            self.fixed_amber_red.min_length = float(params['min_amber_red'])
            self.va_green.min_length = float(params['min_green'])
            self.va_green.max_length = float(params['max_green'])
            self.va_green.green_end = params['green_end']
            self.group_based_red.min_length = float(params['min_red'])
            return None
        else:
            return errors
    
    def any_errors_in_param_input(self, params):
        """Returns a string of first error found in the input, returns None if no errors"""
        if 'min_green' in params:
            if not value_is_number(params['min_green']):
                return "min_green green must be a number"
        else:
            return "No min_green param"

        if 'min_amber_red' in params:
            if not value_is_number(params['min_amber_red']):
                return "min_amber_red green must be a number"
        else:
            return "No min_amber_red param"

        if 'min_red' in params:
            if not value_is_number(params['min_red']):
                return "min_red must be a number"
        else:
            return "No min_red param"

        if 'min_amber' in params:
            if not value_is_number(params['min_amber']):
                return "min_amber must be a number"
        else:
            return "No min_amber param"

        if 'max_green' in params:
            if not value_is_number(params['max_green']):
                return "max_green must be a number"
        else:
            return "No max_green param"

        if 'max_amber_red' in params:
            if not value_is_number(params['max_amber_red']):
                return "max_amber_red must be a number"
        else:
            return "No max_amber_red param"

        if 'max_red' in params:
            if not value_is_number(params['max_red']):
                return "max_red must be a number"
        else:
            return "No max_red param"

        if 'max_amber' in params:
            if not value_is_number(params['max_amber']):
                return "max_amber must be a number"
        else:
            return "No max_amber param"

        # ADD CHCEKING FOR OTHER DATA TYPES

        return None

    #
    #   External objects
    #

    # This is set by the controller
    @property
    def extender(self):
        """Green phase property"""
        return self._extender

    @extender.setter
    def extender(self, ext_extender):
        # Phase commands the green to end -> phase has used the green of previus phase
        self._extender = ext_extender


    @property
    def stat_logger(self):
        """Green phase property"""
        return self._stat_logger

    @stat_logger.setter
    def stat_logger(self, ext_stat_logger):
        # Phase commands the green to end -> phase has used the green of previus phase
        self._stat_logger = ext_stat_logger


    #
    # Set from outside
    # 

    @property
    def request_green(self):
        """True if the group is requesting green"""
        return self._request_green

    @request_green.setter
    def request_green(self, request_green_on):
        """This will be coming from outside (i.e. from detections)"""

        # New requests are accepted if the group is _not_ green
        if not self.group_green_or_amber() and request_green_on:
            self._request_green = True
            for grp in self.side_requests: # DBIK231214 set side requests
                if not self.group_green_or_amber() and request_green_on:
                    grp._request_green = True


        # ... however, the request can be removed at any state
        if not request_green_on:
            self._request_green = False
            for grp in self.side_requests: # DBIK231214 reset side requests
                if not request_green_on:
                    grp._request_green = False


    @property
    def permit_green(self):
        """True if controller has given permission for green"""
        return self._permit_green

    @permit_green.setter
    def permit_green(self, permit_green_on):
        """This will be coming from controller"""
        self._permit_green = permit_green_on


    #
    # Group operation
    #

    def tick(self):
        """Run one time step ahead, will fire transitions if applicable"""
        self.next_state()  # will tranfer state if conditions met

    def end_conflicting_greens_status(self):
        """We ask if there is a request by any conflicting group to end the green"""
        return self.other_group_requests_end_green 

    def end_conflicting_greens(self):
        """We ask all conflicting groups to end their green"""
        for grp in self.conflicting_groups:
            grp['group'].other_group_requests_end_green = True

    def clear_end_conflicting_greens(self):
        """We ask if there is a request by any conflicting group to end the green"""
        self.group.other_group_requests_end_green = False
        return self.other_group_requests_end_green 

    # DBIK 20230915 Check if any non-conflicting group is active
    def any_nonconflicting_green_active(self,nfg):
        for nfg in self.non_conflicting_groups:
            if nfg['group'].state in ['Red_ForceGreen','Red_WaitIntergreen','AmberRed_MinimumTime','Green_MinimumTime', 'Green_Extending']:
               return True
        return False

    # DBIK 20230911 Check if conflicting greens can be terminated
    # DBIK 20230911 Force to red from cb-function to condition
    def can_conflicting_greens_terminated(self):
        """We ask if all conflicting greens can be terminated"""
        for grp in self.conflicting_groups:
            if grp['group'].state in ['Green_Extending']:
               grp['group'].other_group_requests_end_green = True  # Set the request
            if grp['group'].state in ['Green_RemainGreen']:
               if not(self.any_nonconflicting_green_active(grp)):
                  grp['group'].other_group_requests_end_green = True  # Set the request
               else:
                  grp['group'].other_group_requests_end_green = False  # Don't set the request

        for grp in self.conflicting_groups:
            if grp['group'].state in ['Red_ForceGreen','Red_WaitIntergreen','AmberRed_MinimumTime','Green_MinimumTime','Green_Extending']:
                return False  # Set the return value
        return True
        
    #   
    # State transfer conditions
    # 


    def has_green_request(self):
        """A state machine condition
        True if group has a green request"""

        #if self.grp_conf['request_type'] == 'fixed':  
        #   return True
        
        if self.grp_conf['request_type'] == 'fixed': # DBIK231217 Fixed-mode has to set the request, not return True
            self.request_green = True

        # Not fixed and no phase -> depends on variable set by detections
        return self.request_green

    
    def has_green_permission(self):
        return self.permit_green



    def intergreens_passed(self):
        """Returns true if conflict group's intergreens have passed"""
        for grp in self.conflicting_groups:
            if grp['group'].group_on():
                #Group has not even gotten to red -> wait for ig
                return False
            else:
                if grp['delay'] + grp['group'].amber_started_at > self.system_timer.seconds: # DBIK20231023 Intergreen counting start from beginnig of amber 
                    return False # Intergreen not passed -> wait for ig
                
        if self.start_delay_not_passed(self.grp_conf): #  DBIK231208 
           return False
        
        return True # No conflicting intergreens found


    def all_conflicts_red(self):
        """We see if all conflicting groups are red or non blockking state"""
        for grp in self.conflicting_groups:
            if not grp['group'].group_red():
                return False # Found one not red in conflicting -> not all red 
        return True

    # DBIK20231207 Testing start delay
    def start_delay_not_passed(self, grp_conf):  
        """Returns true if start delay of pedestrian signals have passed"""
        if not 'delaying_groups' in grp_conf:
            return False
            # Fixed that this will not grash if not configured 
            # FIXME: Should be handled in the conf read etc  
        if  self.delaying_groups:
            for dgrp in self.delaying_groups:
                    startdelay = grp_conf['delaying_groups'][dgrp.group_name]
                    if self.system_timer.seconds < (dgrp.green_started_at + startdelay): 
                        # print('Wait group: ', self.group_name, 'Deley group: ',dgrp.group_name, 'Delay started: ', dgrp.green_started_at, 'Start delay: ', startdelay)  
                        return True # Start delay passed
        return False
    
    #
    # Group status functions
    # 
    def group_breakpoint(self, grpid, curdefstate, prevdefstate, change):
        """Creates a breakpoint for debugging a given signal group state or state change"""
        if self.group_name == grpid:
            if not(change): 
                if self.state == curstate:
                    SetBreakPoint = True
                    print('Breakpoint at Grp: ',self.group_name,' State: ',self.state)
            else: 
                if (self.prev_state != self.state) and (self.prev_state == prevdefstate): #   and ((self.state == curdefstate) or (curdefstate == 'Any')):
                    SetBreakPoint = True
                    print('Breakpoint at Grp: ',self.group_name,' Prev State: ',self.prev_state, ' Cur State: ',self.state)


    def group_red(self):
        """Returns true if group is in red state and not going green
            i.e. the group is Amber, MinRed, CanEnd or ForceGreen
        """
        isred = False
        par_st = self.state.split('_')[0] # parent state
        # going red ->  red
        if par_st == 'Amber':
            return True
        
        # Red and not transitin to other state -> is red  'DBIK Red_ForceGreen' included 13.3.23
        if self.state in ['Red_Init', 'Red_MinimumTime', 'Red_CanEnd', 'Red_ForceGreen']: 
            isred = True
        #print("isred:", isred)
        return isred

    def group_green(self):
        """Returns true if group is in green state"""
        par_st = self.state.split('_')[0]
        if par_st == 'Green':
            return True
        else:
            return False
        
    def group_on(self):
        """Returns true if phase is
        1) green,
        2) going green (AmberRed) or
        3) ending green (Amber)"""
        par_st = self.state.split('_')[0]
        is_on = par_st in ('Green', 'Amber', 'AmberRed')

        # is_on = self.is_Green or self.is_Amber or self.is_AmberRed
        return is_on

    def group_main_state_changed(self,newstate,curstate,prevstate):
        cur_st = curstate.split('_')[0]
        prev_st = prevstate.split('_')[0]
        if (cur_st == newstate) or (newstate == 'any'):
            if prev_st != newstate:
               return True
        return False
    
    def group_sub_state_changed(self,newstate,curstate,prevstate):
        if (curstate == newstate) or (newstate == 'Any'):
            if prevstate != curstate:
               return curstate
            else:
               return 'None'
        return 'None'

    def group_green_or_amber(self):
        """Returns true if phase is
        1) green or
        2) Amber
        """
        par_st = self.state.split('_')[0]
        is_on = par_st in ('Green', 'Amber')

        # is_on = self.is_Green or self.is_Amber or self.is_AmberRed
        return is_on
    
    def group_red_started(self):
        """Returns true if red signal has started"""
        
        is_started = False
        if self.state in ['Red_MinimumTime']: #  and self.prev_state in ['Amber']:
            is_started = True

        return is_started

    #
    # Controller conditions query these
    #
    def is_in_phase_min_time(self):
        if self.state in ['Red_WaitIntergreen','AmberRed_MinimumTime'] or \
           ((self.state in ['Green_MinimumTime','Green_Extending','Green_RemainGreen']) and 
           (self.system_timer.seconds - self.green_started_at < 3.0)):
            return True
        return False
    
    def phase_min_time_reached2(self):
        phasetime = self.system_timer.seconds - self.phase_started_at
        if (self.state in ['Green_MinimumTime','Green_Extending','Green_RemainGreen']) and (phasetime > 3.0):
            return phasetime
        return 0.0
    
    def phase_min_time_reached(self):
        if self.green_started_at > self.phase_started_at:
            phasetime = self.system_timer.seconds - self.green_started_at
        else:
            phasetime = self.system_timer.seconds - self.phase_started_at

        if (self.state in ['Green_MinimumTime','Green_Extending','Green_RemainGreen']) and (phasetime > 3.0):
            return phasetime
        return 0.0

    def min_green_end(self):
        """
            Returns true if green after min green
            That is: we are extending or remain green
        """
        # DBIK20231013 The End of MinGreen is detected by state current state and the previous state
        if self.prev_state in ['Any'] and self.state in ['Green_Extending','Green_RemainGreen']: # DBIK20231013 
        
        # if self.prev_state in ['Any'] and self.state in ['Green_Extending','Green_RemainGreen']: # DBIK20231013 
        
        # if self.state in ['Green_Extending','Green_RemainGreen']:    # DBIK231129  Test
        # if self.state in not['Red_ForceGreen','Red_WaitIntergreen','Green_MinimumTime']:
        
        # if (self.state=='Green_Extending') or (self.state=='Green_RemainGreen'): # DBIK20231012 
        # Red_CanEnd','Red_MinimumTime', 'Red_CanEnd', 
            return True
        else:
            return False

    def is_in_min_green(self):
        """True if group is in min green"""
        # if self.state=='Green_MinimumTime':
        if self.state in ['Red_WaitIntergreen','AmberRed_MinimumTime','Green_MinimumTime']:
            return True
        else:
            return False
        
    def is_not_in_min_green(self):
        """True if group is in min green"""
        if self.state!='Green_MinimumTime':
            return True
        else:
            return False
        
    # DBIK231129 New function for detecting if a green signal is starting  
    def is_starting(self):
        """True if group if the group has started transition to green"""
        if self.state in ['Red_WaitIntergreen','AmberRed_MinimumTime']:
            return True
        else:
            return False

        

    # DBIK230908 New function for detecting if active green has been passed    
    def active_green_passed(self):
        """
            Returns true if green after active green
            That is: we are in remain green, yellow, minred, redreq
        """
        if self.state in ['Green_RemainGreen','Amber_MinimumTime', 'Red_MinimumTime', 'Red_CanEnd']:
        # DBIK20231016 Looking for a given change of state, not state 
        # if self.prev_state in ['Green_MinimumTime','Green_Extending'] and self.state in ['Green_RemainGreen']: # DBIK20231016     
            return True
        else:
            return False
        
    # DBIK231127 New function for detecting if all conflicting active green has been paased    
    def conflicting_active_green_passed(self):
        """
            Returns true if green after all conflicting active greens has passed
            That is: they are in remain green, yellow, minred, redreq
        """
        active_conf_greens_passed = True
        for grp in self.conflicting_groups:
            if not grp['group'].state in ['Green_RemainGreen','Amber_MinimumTime', 'Red_MinimumTime', 'Red_CanEnd']:
                active_conf_greens_passed = False  # Found one conflicting active green signal
        return active_conf_greens_passed  
    
    # DBIK231204 New function for removing conflicting green permissions    
    def remove_conflicting_green_permissions(self):
        """
        Removes green permissions that are in conflict with a new one
        """
        for grp in self.conflicting_groups:
            grp['group'].permit_green = False  # Found one conflicting active green
    
    
class FixedTime(Machine):
    """Fixed time state machine"""

    def __init__(self, system_timer, group, min_length):
        self.group = group
        self.system_timer = system_timer
        self.min_length = min_length  # Seconds
        self.min_started_at = 0

        states = [
            {'name': 'Init', 'on_enter': self.init_start_cb},
            {'name': 'MinimumTime', 'on_enter': self.min_start_cb},
            {'name': 'Exit', 'on_enter': self.exit_start_cb}
            ]
        transitions = [
            {
                'trigger': 'next_state',
                'source': 'Init',
                'dest': 'MinimumTime'
            },
            {
                'trigger': 'next_state',
                'source': 'MinimumTime',
                'dest': 'Exit',
                'conditions': [self.min_time_passed]
            }
        ]
        initial = 'Init'
        # Note, this deorates this object by passing self...
        Machine.__init__(
            self,
            states=states,
            transitions=transitions,
            initial=initial,
            auto_transitions=False
            )



    # conditions
    def min_time_passed(self):
        """
        Returns true if minimum time is used
        This is based on number of calls if in
        "update mode" ("full speed")
        """
        # Note: this is imitted if the unit is used as an web interface template, might find a better way
        if self.system_timer:
            return bool(self.min_started_at + self.min_length < self.system_timer.seconds)
        else:
            return False
        #return bool(self.steps_left < 0)
        #return False


    # Callbacks
    def min_start_cb(self):
        # Note: this is imitted if the unit is used as an web interface template, might find a better way
        if self.system_timer:
            self.min_started_at = self.system_timer.seconds
        #if self.group.stat_logger:
        #    self.group.stat_logger.add_data(self.group, self.group.state)
        if self.group.instant_transfer:
            self.next_state() #group?

    def exit_start_cb(self):
        if self.group.stat_logger:
            self.group.stat_logger.add_data(self.group, self.group.state)
        #if self.group.state == 'Green_Exit':
        #    self.group.request_green = False  # requests coming after this are counted
        #self.group.next_state()  #else this happens only on next update
        if self.group.instant_transfer:
            self.group.next_state()


    def init_start_cb(self):
        #pass
        # FIX ME, should be in va_green....
        if self.group.state == 'Green_Init':
            self.group.request_green = False  # requests have been given green
        if self.group.stat_logger:
            self.group.stat_logger.add_data(self.group, self.group.state)
        if self.group.instant_transfer:
            self.group.next_state()




class VehicleActuated(FixedTime):
    """ Extends the operatios of fixed timer by adding the extension
        This is intended to be used as a substate machine for green state
    """
    def __init__(self, system_timer, group, min_length, max_length, green_end):
        # Note: min_length is now the min_length (superclass)
        super(VehicleActuated, self).__init__(system_timer, group, min_length)
        # Additional to VA
        self.max_length = max_length
        self.green_end = green_end # Modes: after_ext, remain


        # We don't go to exit without extension
        self.remove_transition(trigger='next_state', dest='Exit')


        # WARNING: I have no idea why state callback is never executed
        # This is not in transition instead, would be:
        #self.add_state('Extending', on_enter=self.extension_start_cb)
        self.add_state('Extending')
        self.add_state('RemainGreen')

        # After minimim, we always go to extending state
        self.add_transition(trigger='next_state',
                            source='MinimumTime',
                            dest='Extending',
                            conditions=[self.min_time_passed],
                            after=self.extension_start_cb,
                            )
        # Extending stops at green end at:
        # 1) end of extensions AND after_ext set OR
        # 2) passing of maximum time
        self.add_transition(trigger='next_state',
                            source='Extending',
                            dest='Exit',
                            conditions=[self.external_not_extending, self.terminate_after_ext_mode],
                            )
        # Extension can go to RemainGreen state if ŕemain set and extensions end
        self.add_transition(trigger='next_state',
                            source='Extending',
                            dest='RemainGreen',
                            conditions=[self.external_not_extending, self.remain_green_mode]
                            )
        # Maximum time and no remain green -> exit
        self.add_transition(trigger='next_state',
                            source='Extending',
                            dest='Exit',
                            conditions=[self.max_time_passed, self.terminate_after_ext_mode],
                            # conditions=[self.max_time_passed], # DBIK20231018 Mode is not affecting max time termination
                            )
        # Maximum time but there is remain green -> RemainGreen
        self.add_transition(trigger='next_state',
                            source='Extending',
                            dest='RemainGreen',
                            conditions=[self.max_time_passed, self.remain_green_mode],
                            )
                
        # Remain green go back to to Extending if EXT=ON // DBIK 12.4.23
        self.add_transition(trigger='next_state',
                            source='RemainGreen',
                            dest='Extending',
                            # conditions=[self.external_extending]
                            conditions=[self.external_extending, self.extension_repetitive] # DBIK20231018 We should add one shot mode extension mode
                            )


        # Remain green ends if any conflicting signal group has request // DBIK 7.9.23
        # TO BE FIXED, do not terminate signal group if is not in conflict currently active green" DBIK 7.9.23
        self.add_transition(trigger='next_state',
                            source='RemainGreen',
                            dest='Exit',
                            conditions=[self.other_group_requests_end_green]
                            )

        # Note: One should check the order of applying the transfers?



    # Conditional: external extension
    def external_extending(self):  
        """We get this conditional from external extender"""       
        ret = False
        if self.group.extender: 
           ret = ret or self.group.extender.extend        
        if self.group.e3extender: 
           ret = ret or self.group.e3extender.extend 
        return ret 
                
    def external_not_extending(self):
        """We get this conditional from external extender"""
        ret = self.external_extending()
        return not(ret) 
    
    def extension_repetitive (self):
        """We defined if extension is one shot or can be repeated"""
        return False
   

    def max_time_passed(self):
        """No matter what the extender does, cut to max"""
        return bool(self.min_started_at+self.max_length < self.system_timer.seconds)

    # this is set by controller
    def other_group_requests_end_green(self):
        #print("Other phase req:", self.group.other_phase_requests)
        return self.group.other_group_requests_end_green

    # set by conf
    def terminate_after_ext_mode(self):
        return bool(self.green_end == 'after_ext')

    def remain_green_mode(self):
        return bool(self.green_end == 'remain')


    #callbacks
    def extension_start_cb(self):
        if self.group.stat_logger:
            self.group.stat_logger.add_data(self.group, self.group.state)


class GroupBasedRed(FixedTime):
    """This implements the group control red with intermediate steps"""
    def __init__(self, system_timer, group, min_length):
        super(GroupBasedRed, self).__init__(system_timer, group, min_length)
        self.system_timer = system_timer
        self.group = group
        self.min_length = min_length
        
        # After minimum red, new states will be added this tranfer should
        # not happen
        self.remove_transition(trigger='next_state', dest='Exit')

        # in this state we can end the red, however, we wait for
        # 1) Request and 2) Permission
        # This refers to B, C or E in trad controller (depending on req)
        self.add_state('CanEnd')
        # At this phase the group tries to force conflict groups to go green
        # This refers to F in trad contoller
        self.add_state('ForceGreen')

        # All conflicts are enging or ended their green, however, 
        # We still have to wait for intergreens to have passed
        # This refers to G green in trad controller
        self.add_state('WaitIntergreen')
        
        # After min red has passed -> we can end this red
        self.add_transition(trigger='next_state',
                            source='MinimumTime',
                            dest='CanEnd',
                            conditions=[self.min_time_passed],
                            after=self.can_start_cb
                            )

        # if we have request and permisison -> we try to end conflicting greens
        #self.add_transition(trigger='next_state',
        #                    source='CanEnd',
        #                    dest='ForceGreen',
        #                    conditions=[self.group.has_green_request, self.group.has_green_permission],
        #                    after=self.force_green_cb
        #                    )
        
        # DBIK230911 Callback function shifted into transition condition called at every uodate
        self.add_transition(trigger='next_state',
                            source='CanEnd',
                            dest='ForceGreen',
                            conditions=[self.group.has_green_request, self.group.has_green_permission],  # self.group.can_conflicting_greens_terminated  DBIK230920 Next phase started too early, previous phase not fully served   
                            # conditions=[self.group.has_green_request, self.group.has_green_permission],  # DBIK230920 Get stucked into the f-state                    
                            after=self.force_green_cb  # DBIK 20231010 Test move Force Green to IG
                            )

        # all conflicts red -> we wait for intergreens (if any)
        self.add_transition(trigger='next_state',
                            source='ForceGreen',
                            dest='WaitIntergreen',
                            conditions=[self.group.all_conflicts_red],
                            after=self.wait_intergreen_cb  # DBIK 20231010 Test move Force Green to IG
                            )

        # all conflicts red -> we wait for intergreens (if any)
        self.add_transition(trigger='next_state',
                            source='WaitIntergreen',
                            dest='Exit',
                            # conditions=[self.group.intergreens_passed,self.group.start_delay_passed],
                            conditions=[self.group.intergreens_passed],
                            after=self.exit_start_cb
                            )


    #callbacks
    def can_start_cb(self):
        self.other_group_requests_end_green = False # DBIK 230913 Reset requests from other groups
        if self.group.instant_transfer:
            self.group.next_state()



    def force_green_cb(self):
        # We clear the green end requests
        # That is: this group can be asked to end the green
        # (at remain) only by a request after this state
        if self.group.group_name == 'group1':
           A=1+2        # Debug point DBIK230909
        self.group.other_group_requests_end_green = False
        # Note: these will only end if they are in appropriate state
        self.group.end_conflicting_greens()
        if self.group.instant_transfer:
            self.group.next_state()

    def force_green_doable(self):
        # We clear the green end requests
        # That is: this group can be asked to end the green
        # (at remain) only by a request after this state
        if self.group.group_name == 'group1':
           A=1+2        # Debug point DBIK230909
        self.group.other_group_requests_end_green = False
        # Note: these will only end if they are in appropriate state
        self.group.end_conflicting_greens()
        if self.group.instant_transfer:
            self.group.next_state()        


    def wait_intergreen_cb(self):
        self.force_green_cb()  # DBIK 20231010 Test move Force Green to IG
        if self.group.instant_transfer:
            self.group.next_state()
        




if __name__ == "__main__":
    print("Testing the group ctrl")
    #sg1 = SignalGroup('1')
    #main()
    draw_graphs()
