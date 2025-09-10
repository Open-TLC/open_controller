import os
import asyncio
import json
import time
import argparse
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import nats  # pip install nats-py
from haversine import haversine, Unit

# ---- config ----
INPUT_SUBJECT_OBJECTS = "radar.266.6.objects_port.json"
INPUT_SUBJECT_SIGNAL  = "group.status.266.11"

OUTPUT_SUBJECT_REAL_EXT    = "detector.control.266-g11_safety_ext"
OUTPUT_SUBJECT_REAL_BLOCK  = "detector.control.266-g11_ext_block"
OUTPUT_SUBJECT_EXT_STATUS  = "extender.status.266-g11"

THRESHOLD_M           = 30.0
NATS_URL              = "nats://10.8.0.204"
STOPLINE_LAT          = 60.164398019050545
STOPLINE_LON          = 24.92070067464535
MAX_NORMAL_EXT        = 8.0
MAX_SAFETY_EXT        = 15.0
OUT_INT               = 1.0
# -----------------


@dataclass
class SharedSignalState:
    """Holds latest 'green' flag from the signal listener."""
    _green: Optional[bool] = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def set_green(self, value: bool):
        async with self._lock:
            self._green = bool(value)

    async def get_green(self) -> Optional[bool]:
        async with self._lock:
            return self._green

def iso_now_ms_no_tz() -> str:
    return datetime.utcnow().isoformat(timespec="milliseconds")

async def publish_status(nc: nats.NATS, subject: str, status: bool):
    payload = {
        "id": subject,
        "tstamp": iso_now_ms_no_tz(),
        "status": status,
    }
    await nc.publish(subject, json.dumps(payload).encode("utf-8"))
    # print(f"[publish] {subject} -> {payload}")


async def publish_control(nc: nats.NATS, subject: str, loop_on: bool):
    payload = {
        "id": subject,
        "tstamp": iso_now_ms_no_tz(),
        "loop_on": loop_on,
    }
    await nc.publish(subject, json.dumps(payload).encode("utf-8"))
    # print(f"[publish] {subject} -> {payload}")


# ---------- Listeners ----------


async def signal_listener(nc: nats.NATS, signal_state: SharedSignalState):
    async def on_msg(msg):  
        data = json.loads(msg.data.decode("utf-8"))
        # "green" iff substate is "1" or "3"
        substate = data.get("substate")
        green = (substate == "1") or (substate == "3")
        #print("grren: ", green)
        await signal_state.set_green(green)
        print(f"[signal_listener] substate={substate!r} -> green={green}")


    await nc.subscribe(INPUT_SUBJECT_SIGNAL, cb=on_msg)
    print(f"[signal_listener] subscribed to '{INPUT_SUBJECT_SIGNAL}'")
# -------------------------------


# ---------- Processor ----------
async def processor(nc: nats.NATS, queue: asyncio.Queue, signal_state: SharedSignalState, threshold_m: float):
    print("[processor] started")
    last_green: Optional[bool] = None
    last_state: Optional[str] = None
    state = "Red"
    green_started_at = time.time()


    while True:
        
        await asyncio.sleep(0.1)  # Provides time for other async functions
        
        green = await signal_state.get_green()

        # rising edge: last was not True, now is True
        green_started = (green is True) and (last_green is not True)

        if state == "Red":
            if green_started:
                state = "Normal Extension"
                green_started_at = time.time()
                print("[Publish ********************] -> Normal Extension Started", round(green_started_at, 2))
                await publish_control(nc, OUTPUT_SUBJECT_REAL_EXT, True)   # safety extension ON
                await publish_control(nc, OUTPUT_SUBJECT_REAL_BLOCK, True) # block others

        
        if state == "Normal Extension":
            cur_time = time.time()
            green_time = round(cur_time - green_started_at, 2)
            if green_time > MAX_NORMAL_EXT:                
                state = "Safety Extension"
                print("Publish ********************] -> Safety Extension Started, green_time:", green_time)
                

        if state == "Safety Extension":
            cur_time = time.time()
            green_time = round(cur_time - green_started_at, 2)
            if green_time > MAX_SAFETY_EXT:                
                state = "Red"
                print("Publish ********************] -> Green Ended; green_time:", green_time)
                await publish_control(nc, OUTPUT_SUBJECT_REAL_EXT, False)
                await publish_control(nc, OUTPUT_SUBJECT_REAL_BLOCK, False)

        # status print only on change
        if state != last_state or (cur_time - last_output > OUT_INT):
                cur_time = time.time()
                cur_green = round(cur_time - green_started_at, 2)                   
                print(f"[processor] State: {state} | Green={green} | Green time={cur_green}")
                await publish_status(nc, OUTPUT_SUBJECT_EXT_STATUS, state) # send extension status to nats
                last_output = cur_time
        
        last_state = state
        last_green = green

# -------------------------------
 

async def main():
    print("Running Safety Ext Fix v9")
    nc = await nats.connect(NATS_URL)
    print("[main] connected to NATS")

    p = argparse.ArgumentParser(description="Safety extender")
    p.add_argument("--max-ext", type=float,
                   default=float(os.getenv("MAX_EXT", MAX_NORMAL_EXT)),
                   help="Max normal extension in seconds (env: MAX_EXT)")
    p.add_argument("--max-safe", type=float,
                   default=float(os.getenv("MAX_SAFE_EXT", MAX_SAFETY_EXT)),
                   help="Max safety extension in seconds (env: MAX_SAFE_EXT)")

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    signal_state = SharedSignalState()

    # Start listeners
    #await objects_listener(nc, queue)
    await signal_listener(nc, signal_state)

    # Start processor
    proc_task = asyncio.create_task(processor(nc, queue, signal_state, THRESHOLD_M))
    proc_task.add_done_callback(lambda t: print("[processor] done:", repr(t.exception())))

    print("[main] running. Ctrl+C to stop.")
    while True:
        #print("test")
        await asyncio.sleep(1)
    

if __name__ == "__main__":
    asyncio.run(main())
