import asyncio
import json
import nats
from haversine import haversine, Unit

def distance_in_meters(lat1, lon1, lat2, lon2):
    coord1 = (lat1, lon1)
    coord2 = (lat2, lon2)
    return haversine(coord1, coord2, unit=Unit.METERS)

def process_data(objects):
    """
    Do something with one batch of objects.
    Here: compute distance of each vehicle to a fixed stop line.
    """
    stopline_lat = 60.164398019050545
    stopline_lon = 24.92070067464535

    for obj in objects:
        vehicle_id = obj.get("sumo_id")
        vehicle_lat = obj.get("lat")
        vehicle_lon = obj.get("lon")
        if vehicle_lat is None or vehicle_lon is None:
            continue
        dist_m = round(distance_in_meters(stopline_lat, stopline_lon, vehicle_lat, vehicle_lon), 2)
        print(f"id={vehicle_id}, dist_to_stopline={dist_m} m")


async def main():
    nc = await nats.connect("nats://127.0.0.1:4222")
    queue: asyncio.Queue = asyncio.Queue()

    async def message_handler(msg):
        try:
            data = json.loads(msg.data.decode())
            objects = data.get("objects", [])
            await queue.put(objects)   # enqueue for processor
            for obj in objects:
                id = obj.get("sumo_id")
                vehicle_lat = obj.get("lat")
                vehicle_lon = obj.get("lon")
                print("id: ", id, "Lat: ", vehicle_lat, " Lon: " , vehicle_lon)
            
        except Exception as e:
            print("Failed to parse:", e)

    await nc.subscribe("radar.266.6.objects_port.json", cb=message_handler)
    print("Listening on 'radar.266.6.objects_port.json' ...")

    # processor loop runs in parallel
    while True:
        objects = await queue.get()
        try:
            process_data(objects)
        finally:
            queue.task_done()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
