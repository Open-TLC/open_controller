import asyncio
import json
import nats  # pip install nats-py
import math
from pyproj import Transformer
from haversine import haversine, Unit

last_msg = {}
veh_count = 0

def distance_in_meters(lat1, lon1, lat2, lon2):
    coord1 = (lat1, lon1)
    coord2 = (lat2, lon2)
    dist_m = haversine(coord1, coord2, unit=Unit.METERS)
    return dist_m

async def main():
    # Connect to NATS server (adjust if not default localhost)
    nc = await nats.connect("nats://127.0.0.1:4222")

    async def message_handler(msg):
        
        stopline_lat = 60.164398019050545
        stopline_lon = 24.92070067464535

        try:
            data = json.loads(msg.data.decode())
            objects = data.get("objects", [])
            veh_count = 0
            for obj in objects:
                last_msg[key][id] = obj.get("sumo_id")
                last_msg[key][lat] = obj.get("lat")
                last_msg[key][lan] = obj.get("lon")
                veh_count += 1
            print('Last message: ', last_msg)

        except Exception as e:
            print("Failed to parse:", e)

    # Subscribe to the subject
    await nc.subscribe("radar.266.6.objects_port.json", cb=message_handler)


async def process_data():
    
        stopline_lat = 60.164398019050545
        stopline_lon = 24.92070067464535

        veh_count2 = 0
        for key in last_msg:
                vehicle_id =  last_msg[key][id]
                vehicle_lat = last_msg[key][lat]
                vehicle_lon = last_msg[key][lan]
                dist_m2 = round(distance_in_meters(stopline_lat, stopline_lon, vehicle_lat, vehicle_lon),2)
                veh_count2 += 1

                lat_r = round(vehicle_lat,14)
                lon_r = round(vehicle_lon,14)
                print("id: ", vehicle_id, " dist2(m): ", dist_m2)
        last_msg = {}
        veh_count = 0


    
print("Listening on 'radar.266.6.objects_port.json' ...")
# Keep running
while True:
    await asyncio.process_data()
    await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())



