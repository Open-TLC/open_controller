import asyncio
import json
from datetime import datetime
import nats  # pip install nats-py

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

    # Valitse testattava kanava
    subject = OUTPUT_SUBJECT_EXT_SAFETY

    # Luo yksinkertainen viesti
    payload = {
        "id": subject,
        "tstamp": iso_now_ms_no_tz(),
        "status": True
    }

    # Lähetä viesti
    await publish_message(nc, subject, payload)

    print(f"Message published to {subject}")
    await nc.close()


if __name__ == "__main__":
    asyncio.run(main())
