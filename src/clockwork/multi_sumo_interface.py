# -*- coding: utf-8 -*-
"""The sumo interface module

This module operates Sumo simulator and applies controller to it
"""
# Copyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#rt random
import sys 
import os
import time
from confread import GlobalConf
# from traffic_controller import TrafficController
from signal_group_controller import PhaseRingController
from timer import Timer
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

def read_conf(file_name):
        """Opens the file and returns values as a dictionary"""
        config = {}
        try:
            with open(file_name) as json_cnf_file:
                config = json.loads(jsmin(json_cnf_file.read()))
        except FileNotFoundError:
            print('File does not exist:', file_name)
            print('Exiting...')
            sys.exit()
        # Should we add sanity check for input?
        return config





# We run the sumo model based on conf dictionery given as parameter
def run_sumo(conf_filename=None, runlog=None):
    """Run sumo with given configuration"""
    print("Running sumo with conf", conf_filename)
    unit_cnf = GlobalConf(filename=conf_filename) # objekti
    controllers_dict = {}

    sys_cnf = unit_cnf.cnf  # dictionary

    # print(sys_cnf)

    # Init system timer from config file DBIK 24.7.23
    
    timer_mode = 'real'
    time_step = 0.1
    time_multiplier = 1.0

    timer_prm = sys_cnf['timer']
    timer_mode = timer_prm['timer_mode']
    time_step = timer_prm['time_step']
    time_multiplier = timer_prm['real_time_multiplier']

    end_time = -1
    if 'max_time' in timer_prm:
        end_time = timer_prm['max_time']

    print('Timer parameters: ', timer_prm)    
    
    system_timer = Timer(timer_prm)
    next_update_time = 0

    dets = []
    exts = []  

    # Init multiple controllers from the cnf-file DBIK202404
    if 'controllers' in sys_cnf.keys():
        print('Controllers found')

    for key in sys_cnf['controllers']:
        print('Controller:', key)
        controllers_dict[key] = {}
        
        if 'controller_file' in sys_cnf['controllers'][key]:
            contr_file = sys_cnf['controllers'][key]['controller_file']
            print('Controller file name:', contr_file)
            
            # Set the controller config dictionary
            if contr_file == 'NUL':
                controller_cnf = sys_cnf['controllers'][key]
            else:  
                controller_cnf = GlobalConf(contr_file)

            # print(' Controller conf:', controller_cnf)

            controller_params = controller_cnf.get_controller_params()

            # print(' Controller params:', controller_params)

            sumo_name = controller_params['sumo_name']
            print('Controller Sumo name:', sumo_name)

            print_status = controller_params['print_status']
            print('Controller print status:', print_status)

            controller_params['name'] = key


            controllers_dict[key]['sumo_name'] = sumo_name
            controllers_dict[key]['print_status'] = print_status
            
            controllers_dict[key]['controller'] = PhaseRingController(controller_params, system_timer)
            
            controllers_dict[key]['controller'].name = key
            cont_name = controllers_dict[key]['controller'].name
            controllers_dict[key]['controller'].prev_status_string = 'start'

            print('Controller Object Name: ',cont_name, 'Initialized')
            print("____")

            print('Controller Dict: ',controllers_dict)

            # We override the outputs if given in conf
            if 'group_outputs' in controller_params:
                sumo_outputs = controller_params['group_outputs']
                controllers_dict[key]['controller'].set_sumo_outputs(sumo_outputs)
                print("We override the sumo outputs from conf with:", sumo_outputs)
                print("******")

            dets += controllers_dict[key]['controller'].req_dets 
            print("dets: ", dets)
            dets += controllers_dict[key]['controller'].ext_dets
            print("dets: ", dets)
            
            exts += controllers_dict[key]['controller'].extenders
            print("exts: ", exts)

    sumo_name = "0" # DEBUG POINT, INIT OK 

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

    sumo_to_dets = get_det_mapping(dets)
    print('sumo to dets: ', sumo_to_dets)

    sumo_loops = traci.inductionloop.getIDList()
    print('sumo loops: ', sumo_loops)

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
    BP2 = False
    last_print = 0
    

    print(system_timer.steps, real_time, next_update_time, sleep_count )

    # traci.vehicle.setLaneChangeMode(vehicleId,256) # Disable lane changing except from Traci

    #######SIMULATION STARTS################################################

    while (traci.simulation.getMinExpectedNumber() > 0) and ((system_timer.steps/10 <= end_time) or (end_time < 0)):

        for vehicleId in traci.vehicle.getIDList():
            traci.vehicle.setSpeedMode(vehicleId,55) # disable right of way check, vehicles can enter the junction, despite queue end
            len = traci.vehicle.getLength(vehicleId)
            if len > 10.0:
                traci.vehicle.setLaneChangeMode(vehicleId,1) # Disable lane changing except from Traci


        real_time = system_timer.real_seconds # DBIK230711  
        
        if real_time >= (next_update_time) or (timer_mode!="real"):  # DBIK230711  timer_mode added 

            next_update_time = next_update_time + time_step # DBIK230720

            # Conditional BREAKPOINT  
            if statusstring == "ebb50b REQ:000010  EXT: 000110  PERM:100110  CUT:111001 (cur:PH:1, next:PH:2) *":
            # if statusstring == "c4ee5bc REQ:1000001  EXT: 0000100  PERM:1111000  OTH:1011101 (cur:PH:1, next:PH:2)":
               BP1 = True

            # MULTI: looping the controllers start here
               
            for key in controllers_dict:

                # Update signal controllers DBIK 20240411
                controllers_dict[key]['controller'].tick()  
                states = controllers_dict[key]['controller'].get_sumo_states()
                sumo_name = controllers_dict[key]['sumo_name']
                traci.trafficlight.setRedYellowGreenState(sumo_name, states)

                # Run-time outputs DBIK 20240411          

                if controllers_dict[key]['print_status']:
                
                    controllers_dict[key]['controller'].prev_status_string = controllers_dict[key]['controller'].cur_status_string 
                    controllers_dict[key]['controller'].cur_status_string = controllers_dict[key]['controller'].get_control_status()
                    clk = system_timer.str_seconds()
                    
                    if ChangesOnly: 
                        prev_stat = controllers_dict[key]['controller'].prev_status_string 
                        cur_stat = controllers_dict[key]['controller'].cur_status_string
                        if (prev_stat != cur_stat) or (system_timer.steps - controllers_dict[key]['controller'].last_print) > 10:
                            print(clk + ' ' + key + ' ' + cur_stat)
                            controllers_dict[key]['controller'].last_print = system_timer.steps
                    else: 
                        print(clk + ' ' + key + ' ' + statusstring)
                    if runlog:
                        runlog.add_line(statusstring)                        

            detections_to_controller(sumo_loops, sumo_to_dets)

            try:
                traci.simulationStep()
            except traci.exceptions.FatalTraCIError:
                print("Fatal error in sumo, exiting")
                break
            
            # print(system_timer.steps, '%.3f' % real_time, '%.3f' % next_update_time, sleep_count, '%.3f' % last_print )

            system_timer.tick() # DBIK230711 imer tick only in the main loop
            
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

    
def get_det_mapping(all_dets):
    loops = traci.inductionloop.getIDList()
    ret = {}
    for loop in loops:
        mapped_dets = []
        for det in all_dets:
            if det.sumo_id == loop:
                mapped_dets.append(det)
        ret[loop] = mapped_dets

    # print ('Loops: ', loops)
    return ret

# Note: params should be removed if it's own class
def detections_to_controller(sumo_loops, sumo_to_dets):

    occlist = [] 
    loop_stat = 'Loops: '
    loop_out_list = ["269_R702R","269_601A"]
    
    for det_id_sumo in sumo_loops:
        vehnum = traci.inductionloop.getLastStepVehicleNumber(det_id_sumo)
        occup = traci.inductionloop.getLastStepOccupancy(det_id_sumo)

        # DBIK  02/2023 Make the detector status list           
        #if (occup > 0):
        #    occlist.append(1)
        #else:
        #    occlist.append(0)      

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


