# This is a microseervice providing the Reputation Server (RS) functionality.
# It is responsible for registering users and issuing certificates.
# All communication with the RA is done through the NATS message broker.
# The RA listens for messages on the following subjects:



import asyncio
import json
from nats.aio.client import Client as NATS
# We use the Radar class from the indicators module
import sys
sys.path.append('src/indicators')
from radar import Radar


# We degine temporary variable for subscribing the Radar messages.
# The conf is as follows (indicators.json):
#    "radar270.1": {
#        "connection": "nats",
#        "type": "radar",
#        "subtype": "sumo",
#        "nats_subject": "radar.270.1.objects_port.json",
#        "notes": "Will subscribe to radar pointing north"
#        }
# This will be defined as dictionary:
RADAR_CONF_270_1 = {
    "connection": "nats",
    "type": "radar",
    "subtype": "sumo",
    "nats_subject": "radar.270.1.objects_port.json",
    "notes": "Will subscribe to radar pointing north"
}

# Parameters for the reputation calculation, these should be read from the config file
# The reputation values are between 0 and 4
MAX_REPUTATION = 4
MIN_REPUTATION = 0
AVERAGE_REPUTATION = 2

# These are in meters
GOOD_MEASUREMENT_THRESHOLD = 0.5
BAD_MEASUREMENT_THRESHOLD = 5.0

# Probapility for changing the reputation value, two directions
CHANGE_PROBABILITY_UP = 1.0
CHANGE_PROBABILITY_DOWN = 1.0

# For the radar, this calculates the position 
#from shapely.geometry import Polygon, Point

#NATS_DEFAULT_SIGN_REQUEST = "ra.sign.request"
NATS_DEFAULT_SIGN_REQUEST = "v2x.rsu.*"
#NATS_DEFAULT_SIGN_RESPONSE = "ra.sign.response"
NATS_DEFAULT_SIGN_RESPONSE = "v2x.rsu.certs"

NATS_DEFAULT_SERVER = "localhost:4222"

class ReputationServer:


    def __init__(self, conf=None):
        # Valid input message types
        self.message_handler = {
            "measurement": self.get_rs_receipt_message,
            "requesting_rs_coupon": self.get_rs_coupon_message
        }


        if not conf:
            self.listen_channel = NATS_DEFAULT_SIGN_REQUEST
            self.response_channel = NATS_DEFAULT_SIGN_RESPONSE
            self.nats_server = NATS_DEFAULT_SERVER
        else:
            self.listen_channel = conf["listen_channel"]
            self.response_channel = conf["response_channel"]
            self.nats_server = conf["nats_server"]
        
        # We store the unprocessed measurement data here
        self.measurement_reports = {}
        
        # Note: in this implemnation we only use one radar
        # FIXME: this should be configurable
        self.radar = Radar("radar270.1", RADAR_CONF_270_1)



    async def run(self):
        # Connett to nats server:
        self.nats = NATS()
        await self.connect_nats() # Exits if fails

 
        # Print init informantion
        print("This is the Reputation Server (RS)")
        print("Listening on message types:", self.message_handler.keys())
        print(f"On channel: {self.listen_channel}")

        # Subscribe to the radar channel
        if self.radar.nats:
            print("Radar available")
            print("Subcribing to radar channel:", self.radar.nats_subject)
            await self.nats.subscribe(self.radar.nats_subject, cb=self.on_radar_message)
        

        # Add the clean up task to the event loop
        asyncio.create_task(self.radar.cleanup_old_data())

        # Subscribe to the v2x channel
        await self.nats.subscribe(self.listen_channel, cb=self.on_veh_message)

        # infinite loop
        while True:
            await asyncio.sleep(1)

    # Radar messages
    async def on_radar_message(self, msg):
        """
        Callback function for handling the radar message
        """
        #print("Received radar message")
        # Parse the message
        message_dict = json.loads(msg.data.decode())
        if message_dict is None:
            print("Message is None")
            return
        #print("Received radar message:", message_dict)
        # Add the data to radar
        self.radar.add_data(message_dict)

    async def on_veh_message(self, msg):
        """
        Callback function for handling the  NATS message
        """
        # Parse the message
        message_dict = json.loads(msg.data.decode())
        if message_dict is None:
            print("Message is None")
            return


        # Select return function in dict
        # And print message type not found if not detines
        if "type" not in message_dict:
            #print(f"Message type not found: {message_dict}")
            return
        mt = message_dict["type"]
        ret_funct = self.message_handler.get(mt, None)
        if ret_funct:
            ret_message = ret_funct(message_dict)
            # Skip the message if there is an error (function returns none in that case)
            if ret_message:
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


    def get_rs_receipt_message(self, msg):
        """
        Returns the request message that RS returns to the vehicle"
        """
        print("Received cert and measurement")
        if not self.report_message_format_correct(msg):
            print("Message format incorrect")
            return None
        if not self.report_certificate_correct(msg["certificate"]):
            print("Certificate incorrect")
            return None

        veh_id = msg["tag"]
        self.measurement_reports[veh_id] = msg["report"]

        receipt_message = {}
        receipt_message["tag"] = veh_id
        receipt_message["type"] = "rs_receipt"
        receipt_message["receipt_sign"] = "RECEIPT_SIGN"
        print("Sending RS receipt:", receipt_message)
        return receipt_message

 
    def get_rs_coupon_message(self, msg):
        """
        Returns the coupong message that RS returns to the vehicle basedon the report

        """

        veh_id = msg["tag"]
        if veh_id not in self.measurement_reports:
            print("No measurement report found for this vehicle")
            return None
        else:
            report = self.measurement_reports[veh_id]

        coupon_message = {}
        coupon_message["tag"] = veh_id
        coupon_message["type"] = "rs_coupon"
        coupon_message["coupon"] = self.get_coupon(report)
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
        if "tag" not in msg:
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

    def get_coupon(self, report_data, previous_reputation=None):
        """
        Calculates and returns a coupon based on the provided report data.

        Args:
            report_data (dict): A dictionary containing the data required to calculate the coupon.

        Returns:
            dict: A dictionary representing the calculated reputation data.
        """
        print("Calculating coupon")
        print("Report data:", report_data)
        if previous_reputation is None:
            previous_reputation = 0
        #new_reputation = self.calculate_reputation_dict(report_data, previous_reputation)
        new_reputation = self.new_reputation(report_data, previous_reputation)
        ret_value = {}
        ret_value["reputation"] = new_reputation
        ret_value["previous_reputation"] = previous_reputation
        return ret_value

    
    # From the documentation:
    #1. If the error is less than GOOD_MEASUREMENT_TRESHOLD 
    #   → increase the reputation, if not MAX_REPUTATION
    #2. If the error is more than BAD_MEASUREMENT_TRESHOLD 
    #   → decrease reputation, if not MIN_REPUTATION
    # 3. If the measurement is between these valuest 
    #   → propose the reputation towards the AVERAGE_REPUTATION (i.e. decrease if reputation is better and increase if worse)
    # Note: the distance could in theory have more dimmensions, but distance in meters is enough for now
    # We use the distance to the closest object in the radar data

    def proposed_reputation(self, closest_dist, previous_reputation):
        """
            We propose the new reputation based on previous reputation and the measurement
            Args:
                closest_dist (float): The distance to the closest object in meters.
                previous_reputation (int): The previous reputation value.
            Returns:
                int: The proposed reputation value.
        """
        # Check if the distance is less than the good measurement threshold
        if closest_dist < GOOD_MEASUREMENT_THRESHOLD:
            # Increase the reputation if it is possible
            new_reputation = min(previous_reputation + 1, MAX_REPUTATION)
        # Check if the distance is more than the bad measurement threshold
        elif closest_dist > BAD_MEASUREMENT_THRESHOLD:
            # Decrease the reputation if it is possible
            new_reputation = max(previous_reputation - 1, MIN_REPUTATION)
        else:
            # Propose the reputation towards the average reputation
            if previous_reputation < AVERAGE_REPUTATION:
                new_reputation = min(previous_reputation + 1, AVERAGE_REPUTATION)
            else:
                new_reputation = max(previous_reputation - 1, AVERAGE_REPUTATION)

        return new_reputation
    

    # We caclulate the proposed reputation with steps:
    # 1, Check that the report data is within the radar coverage (aoi)
    # 2. Get the distance to the closest object in the radar data
    # 3. Calculate the proposed reputation based on the distance and previous reputation
    # 4. Calculate the on propability for the new reputation 
    def new_reputation(self, report_data, previous_reputation):
        """
        Calculate the new reputation based on the report data and previous reputation
        """
        v2x_location = (report_data["lat"], report_data["lon"])
        if not self.radar.is_point_in_aoi(v2x_location):
            #V2X location is not in the area of interest -> no change in reputation
            return previous_reputation
        # Get the closest object in the radar data
        # Note: the radar also adds the distance to the object
        # to the object dictionary ("distance_to_v2x")
        closest_object = self.radar.get_closest_object(v2x_location)
        dist = closest_object["distance_to_v2x"]
        proposed_reputation = self.proposed_reputation(dist, previous_reputation)
        
        # We use the propability to change (or not) the reputation, 
        # based on the direction of change
        if proposed_reputation > previous_reputation:
            # Increase reputation with a probability
            if random.random() < CHANGE_PROBABILITY_UP:
                return proposed_reputation
        elif proposed_reputation < previous_reputation:
            # Decrease reputation with a probability
            if random.random() < CHANGE_PROBABILITY_DOWN:
                return proposed_reputation
        # If no change or probabilities don't allow change, return previous reputation
        return previous_reputation



    

    def calculate_reputation_dict(self, report_data, previous_reputation):
        """
        Calculate the reputation based on the report data
        """        

        # Calculate the reputation based on the report data
        v2x_location = (report_data["lat"], report_data["lon"])
        closest_object = self.radar.get_closest_object(v2x_location)
        if closest_object is None:
            print("No object found")
            return previous_reputation
        # Chose the new reputation values based on the distance to the closest object
        # In radar
        # Note: this is a very simple implementation, we should use a better algorithm
        if closest_object["distance_to_v2x"] < 0.5:
            # Increase the reputation if it is possoble
            new_reputation = max(previous_repitation +1, MAX_REPUTATION)
        elif closest_object["distance_to_v2x"] > 2.0:
            # Decrease the reputation if it is possoble
            new_reputation = max(previous_repitation -1, 0)
        else:
            # No change in reputation
            new_reputation = previous_reputation


        return ret_value



if __name__ == '__main__':
    # Init the service
    ra = ReputationServer()
    asyncio.run(ra.run())
    