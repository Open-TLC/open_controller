import asyncio
import json
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import nats  # pip install nats-py
from haversine import haversine, Unit

# ---- config ----
INPUT_SUBJECT_OBJECTS = "radar.266.6.objects_port.json"
# INPUT_SUBJECT_OBJECTS = "aalto.v2x.vehicles.json"
INPUT_SUBJECT_SIGNAL  = "group.status.266.11"

OUTPUT_SUBJECT_REAL_EXT    = "detector.control.266-g11_safety_ext"
OUTPUT_SUBJECT_REAL_BLOCK  = "detector.control.266-g11_ext_block"

OUTPUT_SUBJECT_EXT_STATUS  = "extender.status.266-g11"  
OUTPUT_SUBJECT_EXT_NORMAL  = "detector.status.266-g11_ext_normal"
OUTPUT_SUBJECT_EXT_SAFETY  = "detector.status.266-g11_ext_safety"

OUTPUT_SUBJECT_V2X_CONTROL = "aalto.v2x.control.json"

THRESHOLD_M           = 30.0
NATS_URL              = "nats://10.8.0.36"   # Lab
# NATS_URL              = "nats://10.8.0.204"  # Field

STOPLINE_LAT          = 60.164398019050545  #Field
STOPLINE_LON          = 24.92070067464535   #Field

# STOPLINE_LAT          = 60.18834  #CarLab
# STOPLINE_LON          = 24.82354  #CarLab

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


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine((lat1, lon1), (lat2, lon2), unit=Unit.METERS)


def find_close_pairs(objects: List[Dict[str, Any]], threshold_m: float) -> List[Dict[str, Any]]:
    """Compute each object's distance to stopline, sort, and collect adjacent pairs under threshold."""
    enriched = []
    for o in objects:
        lat = o.get("lat"); lon = o.get("lon")
        if lat is None or lon is None:
            continue
        dist = distance_m(STOPLINE_LAT, STOPLINE_LON, lat, lon)
        oo = dict(o)
        oo["dist"] = round(dist, 2)
        enriched.append(oo)

    # enriched.sort(key=lambda x: x["dist"], reverse=True)
    enriched.sort(key=lambda x: x["dist"])

    close_pairs: List[Dict[str, Any]] = []
    for i in range(len(enriched) - 1):
        back = enriched[i]
        front = enriched[i + 1]
        gap = round(front["dist"] - back["dist"], 2)
        if gap < threshold_m:
            close_pairs.append({
                "back_id": back.get("sumo_id"),
                "front_id": front.get("sumo_id"),
                "back_dist_m": back["dist"],
                "front_dist_m": front["dist"],
                "gap_m": gap,
            })
    return close_pairs


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



"""# ---------- Listeners ----------
async def objects_listener(nc: nats.NATS, queue: asyncio.Queue):
    async def on_msg(msg):
       
        data = json.loads(msg.data.decode("utf-8"))
        objects = data.get("objects", [])
        await queue.put(objects)
        objcount = data['nobjects']
    
        # print(f"[object_listener] Obj Count: ", objcount)
       
    await nc.subscribe(INPUT_SUBJECT_OBJECTS, cb=on_msg)
    # print(f"[objects_listener] subscribed to '{INPUT_SUBJECT_OBJECTS}'")
"""

# ---------- Listeners ----------
async def objects_listener(nc: nats.NATS, queue: asyncio.Queue):
    async def on_msg(msg):
       
        data = json.loads(msg.data.decode("utf-8"))
        objects = data.get("objects", [])
        
        # await queue.put(objects)
        objcount = data['nobjects']
        
        try:
            queue.get_nowait()          # drop stale
        except asyncio.QueueEmpty:
            pass
        try:
            queue.put_nowait(objects)   # never await here
        except asyncio.QueueFull:
            pass  # shouldn't happen with the get_nowait() above

        objcount = data['nobjects']
        # print(f"[object_listener] Obj Count: ", objcount)
       
    await nc.subscribe(INPUT_SUBJECT_OBJECTS, cb=on_msg)
    # print(f"[objects_listener] subscribed to '{INPUT_SUBJECT_OBJECTS}'")


async def signal_listener(nc: nats.NATS, signal_state: SharedSignalState):
    async def on_msg(msg):
       
        data = json.loads(msg.data.decode("utf-8"))
        # "green" iff substate is "1" or "3"
        substate = data.get("substate")
        green = (substate == "1") or (substate == "3")
        await signal_state.set_green(green)
        print(f"[signal_listener] substate={substate!r} -> green={green}")
       
    await nc.subscribe(INPUT_SUBJECT_SIGNAL, cb=on_msg)
    # print(f"[signal_listener] subscribed to '{INPUT_SUBJECT_SIGNAL}'")
# -------------------------------


# ---------- Processor ----------
async def processor(nc: nats.NATS, queue: asyncio.Queue, signal_state: SharedSignalState, threshold_m: float):
    print("[processor] started")
    last_green = False
    last_state = "Off"
    state = "Red"
    green_started_at = time.time()
    safety_ext_started = False
    last_output = time.time()
    await publish_control(nc, OUTPUT_SUBJECT_REAL_EXT, False) # safety extension OFF
    await publish_control(nc, OUTPUT_SUBJECT_REAL_BLOCK, False) # unblock others
    await publish_control(nc, OUTPUT_SUBJECT_EXT_NORMAL, False)  # Normal extension visualization OFF
    await publish_control(nc, OUTPUT_SUBJECT_EXT_SAFETY, False)  # Safety extension visualization OFF

    while True:
                
        await asyncio.sleep(0.1)  # Provides time for other async functions
        
        objects = await asyncio.wait_for(queue.get(), timeout=10.0) # Get radar data to objects
           
        close_pairs = find_close_pairs(objects, threshold_m) # Find if there are too short gaps between the vehicles 
        safety_ext = len(close_pairs) > 0  # Put safety extension ON
        if safety_ext:
            BO = 1
        green = await signal_state.get_green()  # Get the signal state of group 11
        controlled_vehicles = []

        # rising edge: last was not True, now is True
        green_started = (green is True) and (last_green is not True)

        if state == "Red":
            if green_started:
                state = "Normal Extension Mode"
                green_started_at = time.time()
                print("[processor] -> Green Started at", round(green_started_at, 2))
                await publish_control(nc, OUTPUT_SUBJECT_REAL_EXT, True)   # safety extension ON
                await publish_control(nc, OUTPUT_SUBJECT_REAL_BLOCK, True) 
                await publish_control(nc, OUTPUT_SUBJECT_EXT_NORMAL, True) # Normal extension visualization ON
        
        #if state == "Green Started":
        #    if not safety_ext_started: 
        #        state = "Normal Extension Mode"
        #        await publish_control(nc, OUTPUT_SUBJECT_EXT_NORMAL, True) # Normal extension visualization ON
        #        print("[processor] -> Normal Extension Mode")

        if state == "Normal Extension Mode":
            if safety_ext:
                safety_ext_started = True
                state = "Safety Extension Mode"
                await publish_control(nc, OUTPUT_SUBJECT_EXT_NORMAL, False) # Normal extension visualization OFF
                await publish_control(nc, OUTPUT_SUBJECT_EXT_SAFETY, True)  # Safety extension visualization ON
                print("[processor] -> Safety Extension Mode")
            else:
                #Returns to no ext when the group goes red (maximum reached)
                if not(green):
                    state = "Red"
                    green_ended_at = time.time()
                    green_time = round(green_ended_at - green_started_at, 2)
                    print("[processor] -> Green Ended; green_time:", green_time)
                    await publish_control(nc, OUTPUT_SUBJECT_REAL_EXT, False)   # safety extension OFF
                    await publish_control(nc, OUTPUT_SUBJECT_REAL_BLOCK, False) # unblock others
                    await publish_control(nc, OUTPUT_SUBJECT_EXT_SAFETY, False)  # Safety extension visualization OFF
                    await publish_control(nc, OUTPUT_SUBJECT_EXT_NORMAL, False)  # Normal extension visualization OFF
                    safety_ext_started = False


        if state == "Safety Extension Mode":
            if not safety_ext or not(green):
                state = "Red"
                green_ended_at = time.time()
                green_time = round(green_ended_at - green_started_at, 2)
                print("[processor] -> Green Ended; green_time:", green_time)
                await publish_control(nc, OUTPUT_SUBJECT_REAL_EXT, False)   # safety extension OFF
                await publish_control(nc, OUTPUT_SUBJECT_REAL_BLOCK, False) # unblock others
                await publish_control(nc, OUTPUT_SUBJECT_EXT_SAFETY, False)  # Safety extension visualization OFF
                await publish_control(nc, OUTPUT_SUBJECT_EXT_NORMAL, False)  # Normal extension visualization OFF
                safety_ext_started = False
             
        # status print only on change
        cur_time = time.time()
        cur_green = round(cur_time - green_started_at, 2)  
        
        if (cur_time - last_output > OUT_INT):
            print(f"[processor] State: {state} | Green={green} | Safety_ext_started ={safety_ext_started} | Safety_ext={safety_ext} | Green time={cur_green}")
            last_output = cur_time

            if close_pairs or True:
                    print(f"[processor] {len(close_pairs)} close pair(s) (< {threshold_m} m):")
                    for p in close_pairs:
                        print(f"  {p['back_id']} -> {p['front_id']} | gap={p['gap_m']} m "
                                f"(at {p['back_dist_m']}→{p['front_dist_m']} m)")
            else:
                print(f"[processor] no close pairs (< {threshold_m} m)")


            if state  == "Safety Extension Mode":          
                print(f"[processor] State: {state} | Green={green} | Safety_ext={safety_ext} | Green time={cur_green} ! PUBLISHING V2X CONTROL !!!" )
                await publish_to_vehicles(nc, OUTPUT_SUBJECT_V2X_CONTROL, state) # send v2x control to nats
                if close_pairs:
                    print(f"[processor] {len(close_pairs)} close pair(s) (< {threshold_m} m):")
                    for p in close_pairs:
                        print(f"  {p['back_id']} -> {p['front_id']} | gap={p['gap_m']} m "
                                f"(at {p['back_dist_m']}→{p['front_dist_m']} m)")
                else:
                    print(f"[processor] no close pairs (< {threshold_m} m)")

        if state != last_state:          
            print(f"[processor] State: {state} | Green={green} | Safety_ext={safety_ext} | Green time={cur_green}")
            await publish_status(nc, OUTPUT_SUBJECT_EXT_STATUS, state) # send extension status to nats


        last_state = state
        last_green = green

        
# -------------------------------
 

async def main():
    print("Running Safety Ext V2X v10")
    nc = await nats.connect(NATS_URL)
    print("[main] connected to NATS")

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    signal_state = SharedSignalState()

    # Start listeners
    await objects_listener(nc, queue)
    await signal_listener(nc, signal_state)

    # Start processor
    proc_task = asyncio.create_task(processor(nc, queue, signal_state, THRESHOLD_M))
    proc_task.add_done_callback(lambda t: print("[processor] done:", repr(t.exception())))

    print("[main] running. Ctrl+C to stop.")
    
    while True:
        await asyncio.sleep(1)
    
if __name__ == "__main__":
    asyncio.run(main())
