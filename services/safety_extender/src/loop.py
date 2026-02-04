#!/usr/bin/env python3
import asyncio
import json
from datetime import datetime
import nats  # pip install nats-py
import keyboard  # pip install keyboard

NATS_URL = "localhost"
OUTPUT_SUBJECT = "detector.status.266-11_ext_normal"
OUTPUT_SUBJECT = "detector.status.266-11_ext_safety"

# OUTPUT_SUBJECT = "detector.status.test"


def iso_now_ms_no_tz():
    """Palauttaa UTC-aikaleiman ilman aikavyöhykettä."""
    return datetime.utcnow().isoformat(timespec="microseconds")


async def publish_message(nc, subject, loop_on: bool):
    """Lähettää JSON-viestin NATS:iin."""
    payload = {
        "id": subject,
        "tstamp": iso_now_ms_no_tz(),
        "loop_on": loop_on
    }
    await nc.publish(subject, json.dumps(payload).encode("utf-8"))
    print(f"[publish] {subject} -> {payload}")


async def main():
    print(f"Connecting to NATS at {NATS_URL} ...")
    nc = await nats.connect(NATS_URL)
    print("[OK] Connected to NATS\n")

    loop_on = False  # aloitusarvo

    print("Paina [SPACE] vaihtaaksesi loop_on True/False ja lähetä viesti.")
    print("Paina [ESC] lopettaaksesi.\n")

    while True:
        if keyboard.is_pressed("space"):
            loop_on = not loop_on
            await publish_message(nc, OUTPUT_SUBJECT, loop_on)
            print(f"loop_on = {loop_on}\n")
            await asyncio.sleep(0.3)  # pieni viive, ettei tule tuplalähetyksiä

        elif keyboard.is_pressed("esc"):
            print("Lopetetaan...")
            break

        await asyncio.sleep(0.05)

    await nc.close()
    print("Yhteys suljettu.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nKeskeytetty.")
