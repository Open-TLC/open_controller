"""A relay program for subscribing given channels in a NATs servers and relying them to another"""

FROM_NATS_SERVER = "10.8.0.2"
TO_NATS_SERVER = "10.8.0.201"

TOPICS_TO_SUBSCRIBE = ["radar.270.1.objects_port.json", "radar.270.2.objects_port.json", "radar.270.3.objects_port.json"]

import asyncio
from nats.aio.client import Client as NATS

async def main():
    # Connect to the NATS servers
    from_nats = NATS()
    to_nats = NATS()

    await from_nats.connect(f"nats://{FROM_NATS_SERVER}:4222")
    await to_nats.connect(f"nats://{TO_NATS_SERVER}:4222")

    # Subscribe to the topics
    async def message_handler(msg):
        await to_nats.publish(msg.subject, msg.data)

    for topic in TOPICS_TO_SUBSCRIBE:
        await from_nats.subscribe(topic, cb=message_handler)

    # Run the event loop
    try:
        while True:
            await asyncio.sleep(0.1)
    except KeyboardInterrupt:
        pass

    # Close the connections
    await from_nats.close()
    await to_nats.close()

if __name__ == "__main__":
    asyncio.run(main())