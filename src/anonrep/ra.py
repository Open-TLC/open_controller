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

NATS_DEFAULT_SIGN_REQUEST = "ra.sign.request"
NATS_DEFAULT_SIGN_RESPONSE = "ra.sign.response"
NATS_DEFAULT_SERVER = "localhost:4222"

class RegistrationAuthority:
    def __init__(self, conf=None):
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
        self.nats = await self.connect_nats() # Exits if fails

        # Subscribe to the listen channel
        await self.nats.subscribe(self.listen_channel, cb=self.on_message)

    async def on_message(self, msg):
        # Parse the message
        data = json.loads(msg.data.decode())
        print(f"Received a message: {data}")

        # Check if the coupon is valid
        valid_coupon = self.get_signature_message(data["coupon"])

        if not valid_coupon:
            print("Invalid coupon:", data["coupon"])
            return
        else:
            # Publish response
            self.nats.publish(self.response_channel, json.dumps(valid_coupon))
        
    def get_signature_message(self, coupon):
        # Check if the coupon is valid
        # If it is, returns the sicnature message
        # Else, returns None
        return None
    

    async def connect_nats(self):
        try:
            return self.nats.connect(self.nats_server)
        except Exception as e:
            print("Error connecting to NATS server: ", self.nats_server)
            print(e)
            exit(1)
        





if __name__ == '__main__':
    # Init the service
    ra = RegistrationAuthority()
    asyncio.run(ra.run())
    