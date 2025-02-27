# -*- coding: utf-8 -*-
"""The sumo interface module

This module operates Sumo simulator and applies controller to it 
This is an integrated version that doesn't use NATS
"""
# 
# Open Controller, an open source traffic signal control platform
# URL: https://www.opencontroller.org
# Copyright 2023 - 2024 by Conveqs Oy, Kari Koskinen and others
# This program has been released under EUPL-1.2 license which is available at
# URL: https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12
#

import sys
import os
import time
from confread_integrated import GlobalConf
from timer import Timer
sys.path.append('src/clockwork')
from signal_group_controller import PhaseRingController
from extender import StaticExtender



# This will need:
# export PYTHONPATH=$PYTHONPATH:/usr/share/sumo/tools

# Alternatively:
# we need to import python modules from the $SUMO_HOME/tools directory
if 'SUMO_HOME' in os.environ:
    SUMO_TOOLS = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(SUMO_TOOLS)
    import traci
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")

# from sumolib import checkBinary  # noqa
  

#Note these are not in use at sig-group
DEFAULT_ROUTE_FILE = "testmodel/cross.rou.xml"
DEFAULT_SUMO_CNF = "testmodel/cross.sumocfg"
SUMO_BIN_NAME = "sumo"
SUMO_BIN_NAME_GRAPH = "sumo-gui"



# We run the sumo model based on conf dictionery given as parameter
def run_sumo(conf_filename=None, runlog=None):
    """Run sumo with given configuration"""
    print("Running sumo with conf", conf_filename)
    unit_cnf = GlobalConf(filename=conf_filename)

    sys_cnf = unit_cnf.cnf


    sumo_name = "0" # FIX ME
    if 'controller' in sys_cnf.keys():
        if 'sumo_name' in sys_cnf['controller'].keys():
            sumo_name = sys_cnf['controller']['sumo_name']

    # Init system timer from config file DBIK 24.7.23
    timer_mode = 'real'
    time_step = 0.1
    time_multiplier = 1.0

    timer_prm = sys_cnf['timer']
    timer_mode = timer_prm['timer_mode']
    time_step = timer_prm['time_step']
    time_multiplier = timer_prm['real_time_multiplier']
    print("Timer mode:", timer_mode,", Time step:", time_step, ", Multiplier:", time_multiplier)

    system_timer = Timer(timer_prm)
    next_update_time = 0


    controller_cnf = sys_cnf['controller']
    
    traffic_controller = PhaseRingController(controller_cnf, system_timer)
 
    
    # We override the outputs if given in conf
    if 'group_outputs' in sys_cnf['sumo'].keys():
        sumo_outputs = sys_cnf['sumo']['group_outputs']
        print("We override the sumo outputs from conf with:", sumo_outputs)
        traffic_controller.set_sumo_outputs(sumo_outputs)
    
    # Theese are detectors operating with SUMO model
    e1dets = traffic_controller.req_dets + traffic_controller.ext_dets
    e1exts = traffic_controller.extenders
    e3dets = traffic_controller.e3detectors 


    # Graph always if set in conf, and also if param says so
    if sys_cnf['sumo']['graph']:
        sumo_bin = SUMO_BIN_NAME_GRAPH
    else:
        sumo_bin = SUMO_BIN_NAME
    
    # sumo_bin = SUMO_BIN_NAME # Debugging without graphics DBIK 24.7.23

    # Conf is defined in sumo section of conf
    sumo_file = sys_cnf['sumo']['file_name']
    try:
        traci.start([sumo_bin, "-c", sumo_file,
                "--start",
                "--quit-on-end"])
    except Exception as e:
        print("Sumo start failed:", e)
        return

    sumo_to_e1dets = get_e1det_mapping(e1dets)
    print('sumo to e1 dets: ')
    print(sumo_to_e1dets)

    sumo_to_e3dets = get_e3det_mapping(e3dets)
    print('sumo to e3 dets: ')
    print(sumo_to_e3dets)

    sumo_loops = traci.inductionloop.getIDList()
    print('sumo e1 loops: ')
    print(sumo_loops)

    sumo_e3dets = traci.multientryexit.getIDList()
    print('sumo e1 loops: ')
    print(sumo_loops)

    # NEW UPDATE CYCLE   DBIK230724 

    # Start the actual simulation
    step = 0 
    sleep_count = 0
    sleep_count = 0
    system_timer.reset()
    real_time = system_timer.real_seconds # DBIK230713 
    next_update_time = real_time  # DBIK230713
    ChangesOnly = True
    statusstring = ""
    last_print = 0
    BP2 = False
    SUMOSIM = True
    sumovismode = 'sub_states'
    

    print(system_timer.steps, real_time, next_update_time, sleep_count )

    # traci.vehicle.setLaneChangeMode(vehicleId,256) # Disable lane changing except from Traci

    while traci.simulation.getMinExpectedNumber() > 0:

        for vehicleId in traci.vehicle.getIDList():
            traci.vehicle.setSpeedMode(vehicleId,55) # disable right of way check, vehicles can enter the junction, despite queue end
            # traci.vehicle.setColor(vehicleId,(255,0,0))

        real_time = system_timer.real_seconds # DBIK230711  
        
        if real_time >= (next_update_time) or (timer_mode!="real"):  # DBIK230711  timer_mode added 

            next_update_time = next_update_time + time_step # DBIK230720

            if statusstring == "ebb50b REQ:000010  EXT: 000110  PERM:100110  CUT:111001 (cur:PH:1, next:PH:2) *":
            # if statusstring == "c4ee5bc REQ:1000001  EXT: 0000100  PERM:1111000  OTH:1011101 (cur:PH:1, next:PH:2)":
               BP1 = True

            # MULTI: looping the controllers start here
               
            if SUMOSIM:
                Sumo_e1detections_to_controller(sumo_loops, sumo_to_e1dets)
                Sumo_e3detections_to_controller(sumo_e3dets, sumo_to_e3dets, sumovismode)
            else:
                pass
                # Read detections from NATS
            
            traffic_controller.tick()   

            prevstatusstring = statusstring
            statusstring = traffic_controller.get_control_status()
            clk = system_timer.steps/10
            clk = round(clk, 1)

            if sys_cnf['sumo']['print_status']:
               
                if ChangesOnly: 
                    if (prevstatusstring != statusstring) or ((system_timer.steps - last_print) > 10):
                        print(str(clk) + ' ' + statusstring)
                        last_print = system_timer.steps

                else: print(str(clk) + ' ' + statusstring)

            if runlog:
                runlog.add_line(statusstring)

            states = traffic_controller.get_sumo_states()
            ocTLScount = len(states)
            sumo_tls = traci.trafficlight.getControlledLinks(sumo_name)
            SumoTLScount = len(sumo_tls)
            if ocTLScount < SumoTLScount:
                states = 'r' + states  # DBIK20250129 add group 0 ?
            try:
                traci.trafficlight.setRedYellowGreenState(sumo_name, states)
            except:
                print('Error in signal counts: OC count: ',ocTLScount, 'Sumo TLS: ', SumoTLScount)                
                # for index, value in enumerate(sumo_tls):
                #     print('Sumo TLS info: ', index, value)
                #     DB1 = 1

            
            try:
                traci.simulationStep()
            except traci.exceptions.FatalTraCIError:
                print("Fatal error in sumo, exiting")
                break
            
            # print(system_timer.steps, '%.3f' % real_time, '%.3f' % next_update_time, sleep_count )

            system_timer.tick() # DBIK230711 timer tick only in the main loop
            
            sleep_count = 0

        else: 
            time.sleep(0.01) # DBIK230711
            sleep_count += 1 
            system_timer.sleep_tick()
            real_time = system_timer.real_seconds # DBIK230711
            # print(sleep_count, real_time)


    print("Closing traci")
    try:
        traci.close(False)
    except Exception as e:
        print("Traci closed failed:", e)
    sys.stdout.flush()

    print("exit  ")

    
def get_e1det_mapping(all_dets):
    loops = traci.inductionloop.getIDList()
    ret = {}
    for loop in loops:
        mapped_dets = []
        for det in all_dets:
            if det.sumo_id == loop:
                mapped_dets.append(det)
        ret[loop] = mapped_dets
    print ('e1dets: ', loops)
    return ret

def get_e3det_mapping(all_dets):
    e3dets = traci.multientryexit.getIDList()
    ret = {}
    for e3det in e3dets:
        mapped_e3dets = []
        for dete3 in all_dets:
            if dete3.sumo_id == e3det:
                mapped_e3dets.append(dete3)
        ret[e3det] = mapped_e3dets
    print ('e3dets: ', e3dets)
    return ret

# Note: params should be removed if it's own class
def Sumo_e1detections_to_controller(sumo_loops, sumo_to_dets):
    """ Passes the Sumo e1-detector info to the controller detector objects"""

    occlist = [] 
    loop_stat = 'Loops: '
    
    for det_id_sumo in sumo_loops:
        vehnum = traci.inductionloop.getLastStepVehicleNumber(det_id_sumo)
        occup = traci.inductionloop.getLastStepOccupancy(det_id_sumo)

        occstr='x'
        for det in sumo_to_dets[det_id_sumo]:
            if (vehnum > 0) or (occup > 0):   # DBIK 10.22  or (occup > 0):
                det.loop_on = True
                occstr = '1'
                occlist.append(1)               # DBIK 03.23 (det output list to correct place)
            else:
                det.loop_on = False
                occstr = '0'
                occlist.append(0)
            
        
        # loop_stat += det_id_sumo + ' ' + occstr + ', '

        # print(loop_stat)
                   
    # print("SUMO occup:", occlist, end='') 
    # print("SUMO loops:", loop_stat, end='') 


def Sumo_e3detections_to_controller(sumo_e3dets, sumo_to_dets,vismode): #DBIK241113  New function to pass e3 detector info
    """ Passes the Sumo e3-detector info to the controller detector objects"""
    for e3det_id_sumo in sumo_e3dets:
        vehcount = traci.multientryexit.getLastStepVehicleNumber(e3det_id_sumo) 
        e3vehlist = traci.multientryexit.getLastStepVehicleIDs(e3det_id_sumo)     
        vehiclesdict = {}
        for vehid in e3vehlist:
                vehtype  = traci.vehicle.getTypeID(vehid)
                vspeed   = traci.vehicle.getSpeed(vehid)
                vehdict = {}
                vehdict['vtype'] = vehtype               
                vehdict['vspeed'] = vspeed
                vehdict['maxspeed'] = vspeed
                vehdict['vcolor'] = 'gray'
                # DBIK20250211 Get extra info from V2X vehicles
                if (vehtype == 'v2x_type'):
                    TLSinfo = traci.vehicle.getNextTLS(vehid)
                    leaderInfo = traci.vehicle.getLeader(vehid, dist=30.0)
                    leaderSpeed = traci.vehicle.getSpeed(vehid)
                    
                    try:
                        vehdict['TLSno'] = TLSinfo[0][1]
                        vehdict['TLSdist'] = round(TLSinfo[0][2],1)
                    except: 
                        # print('Error: No TLS info')
                        vehdict['TLSno'] = 'NoSig'
                        vehdict['TLSdist'] = -1
                        
                    try:
                        vehdict['leaderId'] = leaderInfo[0]
                        vehdict['leaderDist'] = round(leaderInfo[1],1)
                        vehdict['leaderSpeed'] = round(leaderSpeed)
                    except: 
                        # print('Error: No leader info')
                        vehdict['leaderId'] = 'NoVeh'
                        vehdict['leaderDist'] = -1
                    
                    # if prt:
                        # print("V2X-data:", vehid, ", TLSno:", vehdict['TLSno'], ", TLSdist:", vehdict['TLSdist'],", LeaderId:", vehdict['leaderId'], ", LeaderDist:", vehdict['leaderDist'] )

                vehiclesdict[vehid] = vehdict
                testdict = vehdict

                

        for e3det in sumo_to_dets[e3det_id_sumo]:     
            #e3det.vehcount = vehcount

            SafetyExtMode = False
            if SafetyExtMode:
            
                for veh in e3det.det_vehicles_dict:
                    vehcolor = e3det.det_vehicles_dict[veh]['vcolor']
                    try:
                        set_vehicle_color(veh,vehcolor)
                    except:
                        print('Vehcolor error: ', veh)

                    if vehcolor == 'red':
                        vehspeed = round(e3det.det_vehicles_dict[veh]['vspeed'],1)
                        # vehspeed = 5.0
                        try:
                            traci.vehicle.setSpeed(veh,vehspeed)
                            curspeed = round(traci.vehicle.getSpeed(veh),1)
                            vehdist = round(e3det.det_vehicles_dict[veh]['leaderDist'],1)
                            print('Vehicle: ',veh,' Speed now: ', curspeed,' Set speed to: ',vehspeed, ' Distance:', vehdist)
                        except:
                            print('Veh speed error: ', veh)
                    else:
                        try:
                            traci.vehicle.setSpeed(veh,-1)
                        except:
                            print('Veh speed error -1: ', veh)

            e3det.update_e3_vehicles(vehiclesdict) # DBIK20250225 Check this !!

            e3det.det_vehicles_dict = vehiclesdict
            visgroup = e3det.owngroup_obj

            # print('grp: ',e3det.owngroup_obj.group_name, 'veh dict: ',e3det.det_vehicles_dict)

            # DBIK201118 Visualize signal states with vehicle colors
            if vismode == 'main_states':  
                sumo_indicate_main_signal_state(vehiclesdict,e3det.last_vehicles_dict,visgroup)
            elif vismode == 'sub_states':
                sumo_indicate_sub_signal_state(vehiclesdict,e3det.last_vehicles_dict,visgroup)
            elif vismode == 'req_perm':
                sumo_indicate_req_perm_state(vehiclesdict,e3det.last_vehicles_dict,visgroup)
            e3det.last_vehicles_dict = vehiclesdict


def sumo_indicate_main_signal_state(vehdict,lastvehdict,visgroup):

        # DBIK202408  Set color of vehicles leaving the e3detector   
        for key in lastvehdict:
            if not(key in vehdict):
                try:
                    set_vehicle_color(key,'gray')
                except:
                    # errorcount += 1
                    pass
        
        # DBIK202408  Set color of vehicles at the e3detector when the signal state changes
        if visgroup.group_main_state_changed('Green',visgroup.state,visgroup.prev_state):
            for key in vehdict:
                set_vehicle_color(key,'green')
        elif visgroup.group_main_state_changed('Red',visgroup.state,visgroup.prev_state):
            for key in vehdict:
                set_vehicle_color(key,'red')

        # DBIK202408  Set color of vehicles entering e3detector
        for key in vehdict:
            if not(key in lastvehdict): # a vehicle entering
                if visgroup.group_green_or_amber():
                    set_vehicle_color(key,'green')
                else:
                    set_vehicle_color(key,'red')


def sumo_indicate_sub_signal_state(vehdict,lastvehdict,visgroup):

        # DBIK202408  Set color of vehicles leaving the e3detector   
        for key in lastvehdict:
            if not(key in vehdict):
                try:
                    set_signal_state_to_vehice_color(key,'Out')
                except:
                    # self.errorcount += 1
                    pass
            
        # DBIK202408  Set color of vehicles at the e3detector when the signal state changes
        vis_state = visgroup.group_sub_state_changed('Any',visgroup.state,visgroup.prev_state)
        if vis_state != 'None':
            for key in vehdict:
                set_signal_state_to_vehice_color(key,vis_state)

        for key in vehdict:       
            if not(key in lastvehdict): # a new vehicle entering
                set_signal_state_to_vehice_color(key,visgroup.state)


def sumo_indicate_req_perm_state(vehdict,lastvehdict,visgroup):

        # DBIK202408  Set color of vehicles leaving the e3detector   
        for key in lastvehdict:
            if not(key in vehdict):
                try:
                    set_req_perm_to_vehice_color(key,'Out',owngroup)
                except:
                    # errorcount += 1
                    pass
        
        # DBIK202408  Set color of vehicles at the e3detector when the signal state changes
        vis_state = visgroup.group_sub_state_changed('Any',visgroup.state,visgroup.prev_state)
        if vis_state != 'None':
            for key in vehdict:
                set_req_perm_to_vehice_color(key,vis_state, visgroup)

        for key in vehdict:       
            if not(key in lastvehdict): # a new vehicle entering
                set_req_perm_to_vehice_color(key,visgroup.state, visgroup)

    
def set_signal_state_to_vehice_color(vehid,sigstate):

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


def set_req_perm_to_vehice_color(vehid,sigstate,visgroup):

        if sigstate in ['Red_MinimumTime','Red_CanEnd','Red_ForceGreen']:
            if visgroup.has_green_request():
                traci.vehicle.setColor(vehid,(153,0,0)) # Dark Red
            else:
                traci.vehicle.setColor(vehid,(255,0,0)) # Red

        if sigstate in ['Red_WaitIntergreen','AmberRed_MinimumTime','Green_MinimumTime','Green_Extending','Green_RemainGreen','Amber_MinimumTime']:
            if visgroup.has_green_permission():
                traci.vehicle.setColor(vehid,(0,102,0)) # Dark Green
            else: 
                traci.vehicle.setColor(vehid,(0,255,0)) # Green
        
        if sigstate in ['Out']:
            traci.vehicle.setColor(vehid,(220,220,220)) # Gray


def set_vehicle_color(vehid,vcolor):
        
        if vcolor == "red":
            traci.vehicle.setColor(vehid,(255,0,0))
        elif vcolor == "darkred":
            traci.vehicle.setColor(vehid,(153,0,0))
        elif vcolor == "darkgreen":
            traci.vehicle.setColor(vehid,(0,102,0))
        elif vcolor == "green":
            traci.vehicle.setColor(vehid,(0,255,0))
        elif vcolor == "yellow":
            traci.vehicle.setColor(vehid,(255,255,0))
        elif vcolor == "blue":
            traci.vehicle.setColor(vehid,(0,128,255)) 
        elif vcolor == "pink":
            traci.vehicle.setColor(vehid,(255,0,255))
        elif vcolor == "gray":
            traci.vehicle.setColor(vehid,(220,220,220))


def print_det_status():
    loopcount = traci.inductionloop.getIDCount()
    loops = traci.inductionloop.getIDList()
    print("Found {} loops: {}".format(loopcount, loops))
    for loop_id in loops:
        lane = traci.inductionloop.getLaneID(loop_id)
        avg_speed = traci.inductionloop.getLastStepMeanSpeed(loop_id)
        avg_length = traci.inductionloop.getLastStepMeanLength(loop_id)
        occupancy = traci.inductionloop.getLastStepOccupancy(loop_id)
        vehs = traci.inductionloop.getLastStepVehicleIDs(loop_id)
        veh_count = traci.inductionloop.getLastStepVehicleNumber(loop_id)
        veh_pos = traci.inductionloop.getPosition(loop_id)
        time_since_det = traci.inductionloop.getTimeSinceDetection(loop_id)
        vehdata = traci.inductionloop.getVehicleData(loop_id)
        print("lane:{}, a_speed:{}, occupancy:{}".format(lane, avg_speed, occupancy))



if __name__ == "__main__":
    #main_runsumo()
    #run_sumo("../models/4leg/4leg.json")
    run_sumo()


