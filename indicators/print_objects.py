"""A relay program for subscribing given channels in a NATs servers and relying them to another"""

NATS_SERVER = "10.8.0.201"

TOPICS_TO_SUBSCRIBE = ["radar.270.1.objects_port.json", "radar.270.2.objects_port.json", "radar.270.3.objects_port.json"]

import asyncio
from nats.aio.client import Client as NATS
import json

async def main():
    # Connect to the NATS servers
    nats = NATS()

    await nats.connect(f"nats://{NATS_SERVER}:4222")

    # Subscribe to the topics
    async def message_handler(msg):
        # get tme messages ans convert them into json
        data = json.loads(msg.data.decode())
        for object in data["objects"]:
            # print the objects
            print("L", object['lane'], ":", object)
        print("")
    
    await nats.subscribe(TOPICS_TO_SUBSCRIBE[0], cb=message_handler)

    # Run the event loop
    try:
        while True:
            await asyncio.sleep(0.1)
    except KeyboardInterrupt:
        pass

    # Close the connections
    await nats.close()

if __name__ == "__main__":
    asyncio.run(main())