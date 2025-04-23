# This is a microseervice providing the Registration Authority (RA) functionality.
# It is responsible for registering users and issuing certificates.
# All communication with the RA is done through the NATS message broker.
# The RA listens for messages on the following subjects:
# - ra.register: Register a new user.
# - ra.sign.request: Sign a (blindly) certificate from the user
# - ra.sign.response: Response to the sign request

# The messages coming in are expected to be JSON objects with the following fields:
# {
# 	"source": UNIQUE_ONE_TIME_ID_1,
# 	"coupon": "REPUTATION_COUPON_STRING" 
# }

# The RA will respond to the source with a JSON object with the following fields:
# {
#	"source": UNIQUE_ONE_TIME_ID_1,
#	"certificate": "CERTIFICATE_STRING" 
#}


import asyncio
import json
import os
from nats.aio.client import Client as NATS

#NATS_DEFAULT_SIGN_REQUEST = "ra.sign.request"
NATS_DEFAULT_SIGN_REQUEST = "v2x.rsu.*"
#NATS_DEFAULT_SIGN_RESPONSE = "ra.sign.response"
NATS_DEFAULT_SIGN_RESPONSE = "v2x.rsu.certs"

NATS_DEFAULT_SERVER = "localhost:4222"

class RegistrationAuthority:


    def __init__(self, conf=None):
        # Valid input message types
        self.message_handler = {
            "requesting_rs_receipt": self.get_rs_receipt_message,
            "measurement": self.get_rs_coupon_message
        }


        if not conf:
            self.listen_channel = NATS_DEFAULT_SIGN_REQUEST
            self.response_channel = NATS_DEFAULT_SIGN_RESPONSE
            self.nats_server = NATS_DEFAULT_SERVER
        else:
            self.listen_channel = conf["listen_channel"]
            self.response_channel = conf["response_channel"]
            self.nats_server = conf["nats_server"]
        

    async def run(self):
        # Connett to nats server:
        self.nats = NATS()
        await self.connect_nats() # Exits if fails

        # Print init informantion
        print("This is the Reputation Server (RS)")
        print("Listening on message types:", self.message_handler.keys())
        print(f"On channel: {self.listen_channel}")

        # Subscribe to the listen channel
        await self.nats.subscribe(self.listen_channel, cb=self.on_message)

        # infinite loop
        while True:
            await asyncio.sleep(1)

    async def on_message(self, msg):
        """
        Callback function for handling the  NATS message
        """

        # Parse the message
        message_dict = json.loads(msg.data.decode())
        #print(f"Received a message: {message_dict}")

        # Select return function in dict
        # And print message type not found if not detines
        if "type" not in message_dict:
            #print(f"Message type not found: {message_dict}")
            return
        mt = message_dict["type"]
        ret_funct = self.message_handler.get(mt, None)
        if ret_funct:
            ret_message = ret_funct(message_dict)
            await self.nats.publish(self.response_channel, json.dumps(ret_message).encode())


    async def connect_nats(self):
        "Subfunction to connect to the NATS server"
        try:
            await self.nats.connect(self.nats_server)
        except Exception as e:
            print("Error connecting to NATS server: ", self.nats_server)
            print(e)
            exit(1)        



    #
    # Message types. these are dictonaries containing the message to send
    # The functions are listed in the same order as they are executed in
    # Normal operation: rs_receipt->rs_coupon
    # 


    def get_rs_receipt_message(self, request_message):
        """
        Returns the request message that RS returns to the vehicle"
        """
        print("Received a request for RS receipt")
        veh_id = request_message["id"]
        receipt_message = {}
        receipt_message["id"] = veh_id
        receipt_message["type"] = "rs_receipt"
        receipt_message["receipt_sign"] = "RECEIPT_SIGN"
        print("Sending RS receipt:", receipt_message)
        return receipt_message

 
    def get_rs_coupon_message(self, msg):
        """
        Returns the coupong message that RS returns to the vehicle basedon the report

        """
        print("Received a request for RS coupon with measurement data:" + str(msg))
        if not self.report_message_format_correct(msg):
            print("Message format incorrect")
            return None
        if not self.report_certificate_correct(msg["certificate"]):
            print("Certificate incorrect")
            return None

        veh_id = msg["id"]
        coupon_message = {}
        coupon_message["id"] = veh_id
        coupon_message["type"] = "rs_coupon"
        coupon_message["coupon"] = self.get_coupon(msg['report'])
        print("Sending RS coupon:", coupon_message)
        return coupon_message


    #
    #   Sanity check and signature check functions
    # 
    def report_message_format_correct(self, msg):
        """
        Check the sanity of the report
        """
        # Check if the report is valid
        if "report" not in msg:
            #print("Report not found")
            return False
        if "id" not in msg:
            #print("ID not found")
            return False
        if "type" not in msg:
            #print("Type not found")
            return False
        if "certificate" not in msg:
            #print("Certificate not found")
            return False
        return True


    def report_certificate_correct(self, certificate):
        """
        Check the certificate, returns True if valid
        """
        # FIXME: We call proper function here
        return True
    

    #
    # Reputation calculation functions
    #

    def get_coupon(self, report_data):
        return "COUPON_TEST"


        





if __name__ == '__main__':
    # Init the service
    ra = RegistrationAuthority()
    asyncio.run(ra.run())
    