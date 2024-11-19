# -*- coding: utf-8 -*-
"""The stand alone clockwrk module for running the controller

This module runs the controller in real time and relays the messages
to NATS server in localhost. This is intended to be used with a real contoller
in the field or alternatively with a simulation model.
"""
# Copyright 2023 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

SOFTWARE_NAME = "Open Controller Traffic Indicators"
IMPL_VERSION = "0.1"

RADAR_TEST_TOPIC = "radar.270.1.objects_port.json"

import asyncio
from nats.aio.client import Client as NATS


async def main():
    nats = NATS()
    await nats.connect("nats://localhost:4222")

    async def message_handler(msg):
        subject = msg.subject
        reply = msg.reply
        data = msg.data.decode()
        print(f"Received a message on '{subject} {reply}': {data}")
    await nats.subscribe(RADAR_TEST_TOPIC, cb=message_handler)
    while True:
        await asyncio.sleep(1)



if __name__ == "__main__":
    asyncio.run(main())