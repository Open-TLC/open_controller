import asyncio
import json
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import nats  # pip install nats-py
from haversine import haversine, Unit



OUTPUT_SUBJECT_EXT_STATUS  = "extender.status.266-g11"  
OUTPUT_SUBJECT_EXT_NORMAL  = "detector.state.266.1-g11_ext_normal"
OUTPUT_SUBJECT_EXT_SAFETY  = "detector.state.266.1-g11_ext_safety"

OUTPUT_SUBJECT_V2X_CONTROL = "aalto.v2x.control.json"

# NATS_URL              = "localhost"   # Lab Software in the loop
NATS_URL              = "10.8.0.36"   # Lab

def iso_now_ms_no_tz() -> str:
    return datetime.utcnow().isoformat(timespec="milliseconds")


async def publish_control(nc: nats.NATS, subject: str, loop_on: bool):
    payload = {
        "id": subject,
        "tstamp": iso_now_ms_no_tz(),
        "loop_on": loop_on,
    }
    await nc.publish(subject, json.dumps(payload).encode("utf-8"))
    print(f"[publish] {subject} -> {payload}")


async def publish_status(nc: nats.NATS, subject: str, status: bool):
    payload = {
        "id": subject,
        "tstamp": iso_now_ms_no_tz(),
        "status": status,
    }
    await nc.publish(subject, json.dumps(payload).encode("utf-8"))
    print(f"[publish] {subject} -> {payload}")


async def publish_to_vehicles(nc: nats.NATS, subject: str, status: bool):
    payload = {
        "id": subject,
        "tstamp": iso_now_ms_no_tz(),
        "status": status,
        "vehicles": ["v2x_veh3"]
    }
    await nc.publish(subject, json.dumps(payload).encode("utf-8"))
    print(f"[publish] {subject} -> {payload}")

  
# -------------------------------
 

async def main():
    print("Publish: ")
    nc = await nats.connect(NATS_URL)
    print("[main] connected to NATS")

    OUTPUT_SUBJECT = OUTPUT_SUBJECT_EXT_SAFETY

    await publish_status(nc, OUTPUT_SUBJECT_EXT_SAFETY, True)  

    print("Published: ", OUTPUT_SUBJECT)
    
    
if __name__ == "__main__":
    asyncio.run(main())
