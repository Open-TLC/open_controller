from clockwork.signal_group_controller import PhaseRingController

type E1Reading = tuple[int, float]
type E3Reading = tuple[int, int]


class DetectorConf:
    def __init__(
        self,
        controller: PhaseRingController,
        traci_connection,
        verbose: bool = False,
    ) -> None:
        self.traci_connection = traci_connection

        # Theese are detectors operating with SUMO model
        e1dets = controller.req_dets + controller.ext_dets
        e3dets = controller.e3detectors

        self.sumo_loops = self.traci_connection.inductionloop.getIDList()
        self.sumo_e3dets = self.traci_connection.multientryexit.getIDList()

        self.sumo_to_e1dets = self.get_e1det_mapping(e1dets, verbose=verbose)
        self.sumo_to_e3dets = self.get_e3det_mapping(e3dets, verbose=verbose)

    def get_e1det_mapping(self, all_dets, verbose=True) -> dict[str, list]:
        loops = self.traci_connection.inductionloop.getIDList()
        ret = {}
        for loop in loops:
            mapped_dets = []
            for det in all_dets:
                if det.sumo_id == loop:
                    mapped_dets.append(det)
            ret[loop] = mapped_dets
        if verbose:
            print("e1dets: ", loops)
        return ret

    def get_e3det_mapping(self, all_dets, verbose=True) -> dict[str, list]:
        e3dets = self.traci_connection.multientryexit.getIDList()
        ret = {}
        for e3det in e3dets:
            mapped_e3dets = []
            for dete3 in all_dets:
                if dete3.sumo_id == e3det:
                    mapped_e3dets.append(dete3)
            ret[e3det] = mapped_e3dets
        if verbose:
            print("e3dets: ", e3dets)
        return ret

    def get_e1_readings(self, det_id: str) -> E1Reading:
        """
        get_e1_readings returns readings from e1 detector

        @params
        det_id: str = detector ID

        @return
        int = number of vehicles detected
        float = occupancy rate meaning the rate at which the detector is occupied as percentage of total time
        """
        vehnum = self.traci_connection.inductionloop.getLastStepVehicleNumber(det_id)
        occup = self.traci_connection.inductionloop.getLastStepOccupancy(det_id)
        return vehnum, occup

    def sumo_e1detections_to_controller(self):
        """Passes the Sumo e1-detector info to the controller detector objects"""

        # occlist = []

        for det_id_sumo in self.sumo_loops:
            vehnum, occup = self.get_e1_readings(det_id_sumo)

            for det in self.sumo_to_e1dets[det_id_sumo]:
                if (vehnum > 0) or (occup > 0):  # DBIK 10.22  or (occup > 0):
                    det.loop_on = True
                    # occlist.append(1)  # DBIK 03.23 (det output list to correct place)
                else:
                    det.loop_on = False
                    # occlist.append(0)

    def get_e3_readings(self, det_id: str) -> E3Reading:
        """
        get_e3_readings returns readings for e3 detector

        @param:
        det_id: str = ID of the target e3 detector

        @return:
        int = number of vehicles detected
        int = number of transit vehicles detected
        """
        vehicle_count: int = 0
        transit_count: int = 0
        vehicles_in_detector: list[str] = (
            self.traci_connection.multientryexit.getLastStepVehicleIDs(det_id)
        )
        for vehid in vehicles_in_detector:
            vehicle_count += 1
            vehtype: str = self.traci_connection.vehicle.getTypeID(vehid)

            # FIXME: find actual vehicle types and define transit IDs as a list
            if vehtype == "transit":
                transit_count += 1

        return vehicle_count, transit_count

    def sumo_e3detections_to_controller(
        self,
        vismode: str = "",
        v2x_mode: bool = False,
        verbose: bool = False,
    ):  # DBIK241113  New function to pass e3 detector info
        """Passes the Sumo e3-detector info to the controller detector objects"""
        for e3det_id_sumo in self.sumo_e3dets:
            e3vehlist = self.traci_connection.multientryexit.getLastStepVehicleIDs(
                e3det_id_sumo
            )
            vehiclesdict = {}
            for vehid in e3vehlist:
                vehtype = self.traci_connection.vehicle.getTypeID(vehid)
                vspeed = self.traci_connection.vehicle.getSpeed(vehid)
                vehdict = {}
                vehdict["vtype"] = vehtype
                vehdict["vspeed"] = vspeed
                vehdict["maxspeed"] = vspeed
                vehdict["vcolor"] = "gray"

                TLSinfo = self.traci_connection.vehicle.getNextTLS(vehid)

                try:
                    vehdict["TLSno"] = TLSinfo[0][1]
                    vehdict["TLSdist"] = round(TLSinfo[0][2], 1)
                except:
                    vehdict["TLSno"] = "NoSig"
                    vehdict["TLSdist"] = -1

                if vehtype == "v2x_type":
                    leaderInfo = self.traci_connection.vehicle.getLeader(
                        vehid, dist=30.0
                    )
                    leaderSpeed = self.traci_connection.vehicle.getSpeed(vehid)

                    try:
                        vehdict["leaderId"] = leaderInfo[0]
                        vehdict["leaderDist"] = round(leaderInfo[1], 1)
                        vehdict["leaderSpeed"] = round(leaderSpeed)
                    except:
                        vehdict["leaderId"] = "NoVeh"
                        vehdict["leaderDist"] = -1

                vehiclesdict[vehid] = vehdict

            for e3det in self.sumo_to_e3dets[e3det_id_sumo]:
                if v2x_mode:
                    for veh in e3det.det_vehicles_dict:
                        vehcolor = e3det.det_vehicles_dict[veh]["vcolor"]
                        try:
                            set_vehicle_color(self.traci_connection, veh, vehcolor)
                        except:
                            print("Vehcolor error: ", veh)

                        if vehcolor == "red":
                            vehspeed = round(e3det.det_vehicles_dict[veh]["vspeed"], 1)
                            try:
                                self.traci_connection.vehicle.setSpeed(veh, vehspeed)
                                curspeed = round(
                                    self.traci_connection.vehicle.getSpeed(veh), 1
                                )
                                vehdist = round(
                                    e3det.det_vehicles_dict[veh]["leaderDist"], 1
                                )
                                if verbose:
                                    print(
                                        "Vehicle: ",
                                        veh,
                                        " Speed now: ",
                                        curspeed,
                                        " Set speed to: ",
                                        vehspeed,
                                        " Distance:",
                                        vehdist,
                                    )
                            except:
                                print("Veh speed error: ", veh)
                        else:
                            try:
                                self.traci_connection.vehicle.setSpeed(veh, -1)
                            except:
                                print("Veh speed error -1: ", veh)

                e3det.update_e3_vehicles(vehiclesdict)  # DBIK20250225 Check this !!

                e3det.det_vehicles_dict = vehiclesdict
                visgroup = e3det.owngroup_obj

                # DBIK201118 Visualize signal states with vehicle colors
                if vismode == "main_states":
                    sumo_indicate_main_signal_state(
                        self.traci_connection,
                        vehiclesdict,
                        e3det.last_vehicles_dict,
                        visgroup,
                    )
                elif vismode == "sub_states":
                    sumo_indicate_sub_signal_state(
                        self.traci_connection,
                        vehiclesdict,
                        e3det.last_vehicles_dict,
                        visgroup,
                    )
                elif vismode == "req_perm":
                    sumo_indicate_req_perm_state(
                        self.traci_connection,
                        vehiclesdict,
                        e3det.last_vehicles_dict,
                        visgroup,
                    )
                e3det.last_vehicles_dict = vehiclesdict


def sumo_indicate_main_signal_state(traci_connection, vehdict, lastvehdict, visgroup):
    # DBIK202408  Set color of vehicles leaving the e3detector
    for key in lastvehdict:
        if key not in vehdict:
            try:
                set_vehicle_color(traci_connection, key, "gray")
            except:
                pass

    # DBIK202408  Set color of vehicles at the e3detector when the signal state changes
    if visgroup.group_main_state_changed("Green", visgroup.state, visgroup.prev_state):
        for key in vehdict:
            set_vehicle_color(traci_connection, key, "green")
    elif visgroup.group_main_state_changed("Red", visgroup.state, visgroup.prev_state):
        for key in vehdict:
            set_vehicle_color(traci_connection, key, "red")

    # DBIK202408  Set color of vehicles entering e3detector
    for key in vehdict:
        if key not in lastvehdict:  # a vehicle entering
            if visgroup.group_green_or_amber():
                set_vehicle_color(traci_connection, key, "green")
            else:
                set_vehicle_color(traci_connection, key, "red")


def sumo_indicate_sub_signal_state(
    traci_connection_connection, vehdict, lastvehdict, visgroup
):
    # DBIK202408  Set color of vehicles leaving the e3detector
    for key in lastvehdict:
        if key not in vehdict:
            try:
                set_signal_state_to_vehice_color(
                    traci_connection_connection, key, "Out"
                )
            except:
                pass

    # DBIK202408  Set color of vehicles at the e3detector when the signal state changes
    vis_state = visgroup.group_sub_state_changed(
        "Any", visgroup.state, visgroup.prev_state
    )
    if vis_state != "None":
        for key in vehdict:
            set_signal_state_to_vehice_color(
                traci_connection_connection, key, vis_state
            )

    for key in vehdict:
        if key not in lastvehdict:  # a new vehicle entering
            set_signal_state_to_vehice_color(
                traci_connection_connection, key, visgroup.state
            )


def sumo_indicate_req_perm_state(traci_connection, vehdict, lastvehdict, visgroup):
    # DBIK202408  Set color of vehicles leaving the e3detector
    for key in lastvehdict:
        if key not in vehdict:
            try:
                set_req_perm_to_vehice_color(traci_connection, key, "Out", visgroup)
            except:
                pass

    # DBIK202408  Set color of vehicles at the e3detector when the signal state changes
    vis_state = visgroup.group_sub_state_changed(
        "Any", visgroup.state, visgroup.prev_state
    )
    if vis_state != "None":
        for key in vehdict:
            set_req_perm_to_vehice_color(traci_connection, key, vis_state, visgroup)

    for key in vehdict:
        if key not in lastvehdict:  # a new vehicle entering
            set_req_perm_to_vehice_color(
                traci_connection, key, visgroup.state, visgroup
            )


def set_signal_state_to_vehice_color(traci_connection, vehid, sigstate):
    if sigstate in ["Red_MinimumTime", "Red_CanEnd"]:
        traci_connection.vehicle.setColor(vehid, (153, 0, 0))  # Dark Red
    elif sigstate in ["Red_ForceGreen"]:
        traci_connection.vehicle.setColor(vehid, (255, 0, 0))  # Red
    elif sigstate in ["Green_MinimumTime"]:
        traci_connection.vehicle.setColor(vehid, (0, 102, 0))  # Dark Green
    elif sigstate in ["Green_Extending"]:
        traci_connection.vehicle.setColor(vehid, (0, 255, 0))  # Green
    elif sigstate in ["Green_RemainGreen", "Amber_MinimumTime"]:
        traci_connection.vehicle.setColor(vehid, (0, 128, 255))  # Blue
    elif sigstate in ["Green_RemainGreen"]:
        traci_connection.vehicle.setColor(vehid, (0, 128, 255))  # Blue
    elif sigstate in ["Red_WaitIntergreen", "AmberRed_MinimumTime"]:
        traci_connection.vehicle.setColor(vehid, (255, 0, 255))  # Pink
    elif sigstate in ["Out"]:
        traci_connection.vehicle.setColor(vehid, (220, 220, 220))  # Gray


def set_req_perm_to_vehice_color(traci_connection, vehid, sigstate, visgroup):
    if sigstate in ["Red_MinimumTime", "Red_CanEnd", "Red_ForceGreen"]:
        if visgroup.has_green_request():
            traci_connection.vehicle.setColor(vehid, (153, 0, 0))  # Dark Red
        else:
            traci_connection.vehicle.setColor(vehid, (255, 0, 0))  # Red

    if sigstate in [
        "Red_WaitIntergreen",
        "AmberRed_MinimumTime",
        "Green_MinimumTime",
        "Green_Extending",
        "Green_RemainGreen",
        "Amber_MinimumTime",
    ]:
        if visgroup.has_green_permission():
            traci_connection.vehicle.setColor(vehid, (0, 102, 0))  # Dark Green
        else:
            traci_connection.vehicle.setColor(vehid, (0, 255, 0))  # Green

    if sigstate in ["Out"]:
        traci_connection.vehicle.setColor(vehid, (220, 220, 220))  # Gray


def set_vehicle_color(traci_connection, vehid, vcolor):
    if vcolor == "red":
        traci_connection.vehicle.setColor(vehid, (255, 0, 0))
    elif vcolor == "darkred":
        traci_connection.vehicle.setColor(vehid, (153, 0, 0))
    elif vcolor == "darkgreen":
        traci_connection.vehicle.setColor(vehid, (0, 102, 0))
    elif vcolor == "green":
        traci_connection.vehicle.setColor(vehid, (0, 255, 0))
    elif vcolor == "yellow":
        traci_connection.vehicle.setColor(vehid, (255, 255, 0))
    elif vcolor == "blue":
        traci_connection.vehicle.setColor(vehid, (0, 128, 255))
    elif vcolor == "pink":
        traci_connection.vehicle.setColor(vehid, (255, 0, 255))
    elif vcolor == "gray":
        traci_connection.vehicle.setColor(vehid, (220, 220, 220))
