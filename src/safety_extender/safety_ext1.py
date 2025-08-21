import asyncio
import json
import nats  # pip install nats-py
import math
from pyproj import Transformer
from haversine import haversine, Unit

def latlon_to_xy(latitude, longitude):
    """
    Convert latitude/longitude (degrees) to local x,y in meters
    relative to a reference point (origin_latitude, origin_longitude)
    x = East, y = North
    """
    EARTH_RADIUS_M = 6_371_000.0  # meters
    origin_latitude = 60.164398019050545
    origin_longitude = 24.92070067464535

    # Convert to radians
    lat_rad = math.radians(latitude)
    lon_rad = math.radians(longitude)
    origin_lat_rad = math.radians(origin_latitude)
    origin_lon_rad = math.radians(origin_longitude)

    delta_lat = lat_rad - origin_lat_rad
    delta_lon = lon_rad - origin_lon_rad

    # Approximate local East/North using equirectangular projection
    x = delta_lon * math.cos((lat_rad + origin_lat_rad) / 2.0) * EARTH_RADIUS_M
    y = delta_lat * EARTH_RADIUS_M

    return x, y

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
            for obj in reversed(objects):
                id = obj.get("sumo_id")
                vehicle_lat = obj.get("lat")
                vehicle_lon = obj.get("lon")
            
                x, y = latlon_to_xy(vehicle_lat, vehicle_lon)
                dist_m1 = round(math.sqrt(x**2 + y**2),2)
                # print("id: ", id, "Lat: ", vehicle_lat, " Lon: " , vehicle_lon, f"x={x:.2f} m, y={y:.2f} m" )
                # print("id: ", id, "Lat: ", vehicle_lat, " Lon: "  ,vehicle_lon, " dist1(m): ", dist_m1 )

                lat_r = round(vehicle_lat,14)
                lon_r = round(vehicle_lon,14)
                dist_m2 = round(distance_in_meters(stopline_lat, stopline_lon, vehicle_lat, vehicle_lon),2)
                print("id: ", id, "Lat: ", lat_r, " Lon: " , lon_r, " dist1(m): ", dist_m1, " dist2(m): ", dist_m2)


        except Exception as e:
            print("Failed to parse:", e)

    # Subscribe to the subject
    await nc.subscribe("radar.266.6.objects_port.json", cb=message_handler)

    print("Listening on 'radar.266.6.objects_port.json' ...")
    # Keep running
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
