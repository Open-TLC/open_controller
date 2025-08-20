import asyncio
import json
import nats  # pip install nats-py
import math

def latlon_to_xy(latitude, longitude):
    """
    Convert latitude/longitude (degrees) to local x,y in meters
    relative to a reference point (origin_latitude, origin_longitude)
    x = East, y = North
    """
    EARTH_RADIUS_M = 6_371_000.0  # meters
    origin_latitude = 60.16425246399936
    origin_longitude = 24.920889451536674

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



async def main():
    # Connect to NATS server (adjust if not default localhost)
    nc = await nats.connect("nats://127.0.0.1:4222")

    async def message_handler(msg):
        try:
            data = json.loads(msg.data.decode())
            objects = data.get("objects", [])
            for obj in objects:
                id = obj.get("sumo_id")
                latitude = obj.get("lat")
                longitude = obj.get("lon")
                x, y = latlon_to_xy(latitude, longitude)
                print("id: ", id, 'Lat: ', latitude, " Lon:" , longitude, f"x={x:.2f} m, y={y:.2f} m" )


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
