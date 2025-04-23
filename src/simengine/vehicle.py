# -*- coding: utf-8 -*-
""" 
    Vehicle object type for handling messages between sumo and individual vehicles
    This is used for V2X communications
"""

from transitions import Machine

class Vehicle:

    # These states are for handling the anonymouse reputation messages
    # Data_to_send->waiting_ra_receipt->waiting_for_ra_certificate is for getting correct (blind) signature
    # from the Registration Authority (RA)
    # waiting_for_rs_receipt->wait_rs_coupon is for getting the reputation from the Reputation Server (RS)
    # Receipt steps are needed for creating "virtual session" blocking man in the middle attacks
    # For more information see the paper URL_TO_PAPER FIXME
    states = ['waiting_for_data', 'data_to_send', 'waiting_ra_receipt', 'waiting_for_ra_certificate', 'waiting_for_rs_receipt', 'wait_rs_coupon']

    def __init__(self, id):
        self.id = id
        self.temp_id = None
        self.current_ra_receipt = None
        self.current_rs_receipt = None
        self.messages = []
        self.certificate = None
        self.reputation_coupon = None
        self.coupon_generator = CouponGenerator()
        self.id_generator = UniqueIDGenerator()
        #self.state = VehState()
        # The statemachine (the steps refer to paper, see link above)
        self.machine = Machine(model=self, states=Vehicle.states, initial='waiting_for_data')
        # Triggered by new data (from sumo)
        self.machine.add_transition(trigger='got_data', source='waiting_for_data', dest='data_to_send')
        
        # Sending coupon, waiting to get the receipt (Step 1)
        self.machine.add_transition(trigger='send_coupon', source='data_to_send', dest='waiting_ra_receipt')
        # Got the ra receipt, after confirming, request the certificate (step 3)
        self.machine.add_transition(trigger='sent_identity_to_ra', source='waiting_ra_receipt', dest='waiting_for_ra_certificate')
        # Got the certificate, we start data sending process 
        # First we rquest a receipt from RS (step 5)
        self.machine.add_transition(trigger='request_rs_receipt', source='waiting_for_ra_certificate', dest='waiting_for_rs_receipt')
        # Then we send the measurement data to RS and expect to get back the coupon 
        # for the prooposed new reputation (step 7)
        self.machine.add_transition(trigger='send_data_to_rs', source='waiting_for_rs_receipt', dest='wait_rs_coupon')
        # Get back to the initial state after we got the coupon
        self.machine.add_transition(trigger='got_coupon', source='wait_rs_coupon', dest='waiting_for_data')

        # From all the states we can reset the state machine and start from the beginning
        self.machine.add_transition(trigger='reset', source='*', dest='waiting_for_data', before='reset_data')


    def reset_data(self):
        """When data transfer fails, or any other reason, we reset everything"""
        self.messages = []
        self.certificate = None
        self.temp_id = None
        self.current_ra_receipt = None
        self.current_rs_receipt = None


    def add_data(self, data):
        self.messages.append(data)
        # We basically ignore all data arrifing while in data sending process
        if self.is_waiting_for_data():
            self.got_data()

        #self.state.got_data() # changes the state
        
        # Note: this data has to be cleaned up at some point
        # We don't want to keep all the data in memory
        # FIXME: Implement a cleanup mechanism

    def get_latest_data(self):
        return self.messages[-1]
    
    def get_latest_mearurement_data(self):
        """
            Returns the latest measurement data in serializible format
        """
        out_data = dict(self.get_latest_data())
        del out_data['sumo_loc'] # Wont serialize
        del out_data['lastupdate'] # Wont serialize
        return out_data
    

    #
    # Functions for processing the incoming messages
    # 
    def process_ra_receipt(self, response):
        """
        Processes the certificate from the RA
        """
        self.current_ra_receipt = response

    def process_ra_certificate(self, response):
        """
        Processes the certificate from the RA
        """
        self.certificate = response["certificate"]

    def process_rs_receipt(self, response):
        """
        Processes the certificate from the RA
        """
        self.rurrent_rs_receipt = response

    def process_rs_coupon(self, response):
        """
        Processes the coupon from the RS
        """
        self.reputation_coupon = response["coupon"]
        self.got_coupon() # state change start the next round



    #
    # Message types. these are dictonaries containing the message to send
    # The functions are listed in the same order as they are executed in
    # Normal operation: ra_receipt->ra_certificate->rs_receipt->rs_coupon
    # 
    def get_request_ra_cert_message(self):
        """
        Returns the request message for the registration authority (ra)
        """
        # Will be used untill we get the certificate
        request_message = {}
        request_message["id"] = self.temp_id
        request_message["type"] = "requesting_ra_certificate"
        return request_message

    def get_coupon_message(self):
        """
        Returns the sign request message for the vehicle
        This is to be send to the RA for (blind) signing
        """
        request_message = {}
        self.temp_id = self.id_generator.generate_id()
        request_message["id"] = self.temp_id # Defined in previous state
        request_message["type"] = "client_coupon"
        coupon = self.coupon_generator.get_coupon()
        request_message["coupon"] = coupon
        return request_message


    def get_request_rs_receipt_message(self):
        """
        Returns the request message for the reputation server (rr)
        """
        # Will be used untill we get the certificate
        self.temp_id = self.id_generator.generate_id()
        request_message = {}
        request_message["id"] = self.temp_id
        request_message["type"] = "requesting_ra_certificate"
        return request_message


    def get_measurement_message(self):
        """
        Returns the measurement message for the vehicle
        Note that this cannot be returned until the certificate is signed
        """
        if self.certificate is None:
            raise ValueError("Certificate is not signed yet")
        
        measurement_message = self.get_latest_mearurement_data()
        measurement_message["id"] = self.temp_id
        measurement_message["type"] = "measurement"
        measurement_message["certificate"] = self.certificate
        return measurement_message

    def get_message_to_send(self):
        """
        Returns the message to send depending on the status of the vehicle
        """
        # these ifs are processed in order and each returns if true

        # We are in step 1 and want to send some data, first we establish a session 
        # with the RA
        if self.is_data_to_send():
            self.send_coupon() # state change
            return self.get_coupon_message()

        # We have established a connection to the RA, now we can request the certificate
        if self.current_ra_receipt:
            self.sent_identity_to_ra()
            self.current_ra_receipt = None
            return self.get_request_ra_cert_message()
        
        # We have the certificate, now we can start sending the data to the RS
        if self.is_waiting_for_ra_certificate():
            # The self certificate is set if we have gotten it from the RA
            if self.certificate:
                self.request_rs_receipt()
                return self.get_request_rs_receipt_message()
        # We have the receipt from the RS, now we can send the data
        if self.is_waiting_for_rs_receipt():
            self.send_data_to_rs()
            return self.get_measurement_message()

        # No messages to send
        return None

    def process_incoming_message(self, message):
        """
        Processes the incoming message note that the caller should ensure
        thet the messages are actually intented for this vehicle
        """
        print("Processing incoming message")
        print(message)
        if not "id" in message:
            raise ValueError("Message does not contain id")
        
        if message["id"] != self.temp_id:
            return # Not for us
        
        if message["type"] == "ra_receipt":
            if self.is_waiting_ra_receipt():
                # FIXME: Check the receipt function should be here
                print("Processing RA receipt")
                self.process_ra_receipt(message)
        elif message["type"] == "ra_certificate":
            if self.is_waiting_for_ra_certificate():
                self.process_ra_certificate(message)

        elif message["type"] == "rs_receipt":
            if self.is_waiting_for_rs_receipt():
                self.process_rs_receipt(message)
        elif message["type"] == "rs_coupon":
            if self.is_wait_rs_coupon():
                self.process_rs_coupon(message)


class UniqueIDGenerator:
    def __init__(self):
        self.id = 0

    def generate_id(self):
        self.id += 1
        return self.id
    
class CouponGenerator:
    def __init__(self):
        # FIXME: this should include the coupon from the RS
        # And be generated by the RS
        self.coupon = "THIS IS AN INITIAL COUPON"
    
    def get_coupon(self):
        return self.coupon

