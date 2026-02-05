#!/usr/bin/env python3
import asyncio
import json
from datetime import datetime
import nats  # pip install nats-py
import keyboard  # pip install keyboard

NATS_URL = "10.8.0.36"

# Testikanavat
OUTPUT_SUBJECT_EXT_STATUS  = "extender.status.266-g11"
OUTPUT_SUBJECT_EXT_NORMAL  = "detector.state.266.1-g11_ext_normal"
OUTPUT_SUBJECT_EXT_SAFETY  = "detector.state.266.1-g11_ext_safety"
OUTPUT_SUBJECT_V2X_CONTROL = "aalto.v2x.control.json"


def iso_now_ms_no_tz():
    """Palauttaa UTC-aikaleiman ilman aikavyöhykettä."""
    return datetime.utcnow().isoformat(timespec="milliseconds")


async def publish_message(nc, subject, payload):
    """Julkaisee JSON-paketin NATS-kanavaan."""
    data = json.dumps(payload).encode("utf-8")
    await nc.publish(subject, data)
    print(f"[publish] {subject} -> {payload}")


async def main():
    print("Connecting to NATS...")
    nc = await nats.connect(NATS_URL)
    print("[main] Connected to NATS\n")

    subject = OUTPUT_SUBJECT_EXT_SAFETY
    status = True  # aloitusarvo

    print("Paina [SPACE] vaihtaaksesi status True/False.")
    print("Paina [ESC] lopettaaksesi.\n")

    while True:
        if keyboard.is_pressed("space"):
            status = not status
            payload = {
                "id": subject,
                "tstamp": iso_now_ms_no_tz(),
                "status": status
            }
            await publish_message(nc, subject, payload)
            await asyncio.sleep(0.3)  # pieni viive, ettei tule useita kertoja

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
