import os
import asyncio
import json
import time
import argparse
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import nats  # pip install nats-py


# ---- config ----

DETECTOR_PPEFIX = "detector.control.266."
GROUP_PPEFIX = "group.control.266."

# NATS_URL              = "nats://10.8.0.204"
NATS_URL              = "nats://10.8.0.36"


def iso_now_ms_no_tz() -> str:
    return datetime.utcnow().isoformat(timespec="milliseconds")

async def publish_control(nc: nats.NATS, subject: str, loop_on: bool):
    payload = {
        "id": subject,
        "tstamp": iso_now_ms_no_tz(),
        "loop_on": loop_on,
    }
    await nc.publish(subject, json.dumps(payload).encode("utf-8"))
    # print(f"[publish] {subject} -> {payload}")

# -------------------------------
 
def main():

    print("Running IO-control")
    nc = nats.connect(NATS_URL)
    print("[main] connected to NATS")
    
    OUT_SUBJECT = GROUP_PPEFIX + "1" 

    publish_control(nc, OUT_SUBJECT , True) 

    print('Output Subject: ', OUT_SUBJECT)
        

 