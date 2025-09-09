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
INPUT_SUBJECT_SIGNAL  = "group.status.266.11"

OUTPUT_SUBJECT_REAL_EXT    = "detector.control.266-g11_safety_ext"
OUTPUT_SUBJECT_REAL_BLOCK  = "detector.control.266-g11_ext_block"

THRESHOLD_M           = 30.0
NATS_URL              = "nats://10.8.0.36"
STOPLINE_LAT          = 60.164398019050545
STOPLINE_LON          = 24.92070067464535
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


def iso_now_ms() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

def iso_now_ms_no_tz() -> str:
    # Use naive datetime (no tzinfo), millisecond precision
    return datetime.utcnow().isoformat(timespec="milliseconds")


async def publish_control(nc: nats.NATS, OUTPUT_SUBJECT: str, loop_on: bool):
    payload = {
        "id": OUTPUT_SUBJECT,
        "tstamp": iso_now_ms_no_tz(),
        "loop_on": loop_on,
    }
    await nc.publish(OUTPUT_SUBJECT, json.dumps(payload).encode("utf-8"))
    print(f"[publish] {OUTPUT_SUBJECT} -> loop_on={payload}")


# ---------- Listeners ----------
async def objects_listener(nc: nats.NATS, queue: asyncio.Queue):
    async def on_msg(msg):
        try:
            data = json.loads(msg.data.decode("utf-8"))
            objects = data.get("objects", [])
            await queue.put(objects)
        except Exception as e:
            print("[objects_listener] parse error:", e)

    await nc.subscribe(INPUT_SUBJECT_OBJECTS, cb=on_msg)
    print(f"[objects_listener] subscribed to '{INPUT_SUBJECT_OBJECTS}'")


async def signal_listener(nc: nats.NATS, signal_state: SharedSignalState):
    async def on_msg(msg):
        try:
            data = json.loads(msg.data.decode("utf-8"))

            # Only substate controls green:
            # True  iff substate == "1"
            # False otherwise (including missing)
            substate = data.get("substate")
            green = (substate == "1") or (substate == "3")

            await signal_state.set_green(green)
            print(f"[signal_listener] substate={substate!r} -> green={green}")

        except Exception as e:
            print("[signal_listener] parse error:", e)

    await nc.subscribe(INPUT_SUBJECT_SIGNAL, cb=on_msg)
    print(f"[signal_listener] subscribed to '{INPUT_SUBJECT_SIGNAL}'")


    async def on_msg(msg):
        try:
            data = json.loads(msg.data.decode("utf-8"))
            # green = bool(data.get("green", False))
            green = data.get("substate") == "1" or data.get("substate") == "3"
            await signal_state.set_green(green)
            print(f"[signal_listener] green={green}")
        except Exception as e:
            print("[signal_listener] parse error:", e)

    await nc.subscribe(INPUT_SUBJECT_SIGNAL, cb=on_msg)
    print(f"[signal_listener] subscribed to '{INPUT_SUBJECT_SIGNAL}'")
# -------------------------------


# ---------- Processor ----------
async def processor(nc: nats.NATS, queue: asyncio.Queue, signal_state: SharedSignalState, threshold_m: float):
    last_green: false
    state = "Off"
    while True:
        try:
            green = await signal_state.get_green()
            
            green_started = green and not(last_green) 
            if green_started:
                state = "Green Extension Started"
                green_startet_at = round(time.time(),2)
                print ("Current state: ", state, "at: ", green_startet_at)
                await publish_control(nc, OUTPUT_SUBJECT_REAL_EXT, True)  # Set the safety extension ON
                await publish_control(nc, OUTPUT_SUBJECT_REAL_BLOCK, True)  # Block other extensions
                
            curtime = round(time.time(),2)
            green_time = round(curtime - green_startet_at,2)
            print ("Green Time: ", green_time)

            if green_time > 15.0: 
                state = "Green Ended"
                green_ended_at = round(time.time(),2)
                green_time = round(green_ended_at - green_startet_at,2)
                print ("Current state: ", state, "at: ", green_ended_at, "Green time: ", green_time)
                await publish_control(nc, OUTPUT_SUBJECT_REAL_EXT, False)  # Set the safety extension OFF
                await publish_control(nc, OUTPUT_SUBJECT_REAL_BLOCK, False) # Release the block of other extensions   
                BP = 1 
            
            last_green = green

        finally:
            queue.task_done()
# -------------------------------


async def main():
    nc = await nats.connect(NATS_URL)
    print("[main] connected to NATS")

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    signal_state = SharedSignalState()

    # Start both listeners
    await objects_listener(nc, queue)
    await signal_listener(nc, signal_state)

    # Start processor
    proc_task = asyncio.create_task(processor(nc, queue, signal_state, THRESHOLD_M))

    print("[main] running. Ctrl+C to stop.")
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        print("\n[main] stopping…")
    finally:
        proc_task.cancel()
        await nc.drain()
        await nc.close()
        print("[main] shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
