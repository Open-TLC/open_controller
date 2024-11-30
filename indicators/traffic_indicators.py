"""The stand alone clockwrk module for running the traffic indicators.

This component will connect to gieven data sources and calculate the traffic indicators.

"""
# Copyright 2023 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

SOFTWARE_NAME = "Open Controller Traffic Indicators"
IMPL_VERSION = "0.1"

RADAR_TEST_TOPIC = "radar.270.1.objects_port.json"
CONF_FILE = "models/testmodel/indicators.json"

import asyncio
from nats.aio.client import Client as NATS
import argparse
from confread import GlobalConf


async def main():
    command_line_params = read_command_line()
    config = GlobalConf(command_line_params=command_line_params, conf=command_line_params.conf)
    print("Config:")
    print(config)
    exit(0)
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


def read_command_line():
    """Returns parsed command line arguments
    """

    operation_description = """
    Runs the sumo in real time and relays the detector and group states
    to a nats-server
    """
    parser = argparse.ArgumentParser(
        description=operation_description)

    vers = SOFTWARE_NAME + " v. " + IMPL_VERSION
    parser.add_argument('--version', action='version', version=vers)

    parser.add_argument('--conf',
                                help='Configuration parameters '
                                    '(default: default.json)',
                                required=False)

   
    parser.add_argument('--nats-server',
                                help='Nats server address ',
                                required=False)
    parser.add_argument('--nats-port',
                                help='Nats server port ',
                                required=False)
    
    args = parser.parse_args()

    return args

if __name__ == "__main__":
    asyncio.run(main())