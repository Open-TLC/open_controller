import asyncio
import json
import subprocess
import sys
import nats

NATS_SERVER = "nats://10.8.0.36:4222"
SUBJECT = "oc.status.266"
WORKDIR = r"C:\DEVE\open_controller"

CREATE_NEW_CONSOLE = subprocess.CREATE_NEW_CONSOLE

cmd1 = [
    sys.executable,
    "services/simengine/src/simengine.py",
    "--nats-server", "10.8.0.36",
    "--conf", "models/JS_266_DEMO/sim/JS_266_sim_hwil_demo.json",
    "--sumo-conf", "models/JS_266_DEMO/cfgFiles/JS_266-267_HWIL.sumocfg",
    "--graph"
]

cmd2 = [
    sys.executable,
    "services/control_engine/src/clockwork.py",
    "--nats-server", "10.8.0.36",
    "--conf-file=models/JS_266_DEMO/contr/JS1_266_DEMO_042026.json"
]

cmd3 = [
    sys.executable,
    "services/indicators/src/traffic_indicators.py",
    "--nats-server", "10.8.0.36",
    "--conf", "models/JS_266_DEMO/ind/JS_266-267_live_radars.json"
]

processes = []
started = False


def start_processes():
    global started

    if started:
        print("Processes already started. Ignoring ready=True.")
        return

    started = True

    print("ready=True received. Starting processes...")

    for cmd in [cmd1, cmd2, cmd3]:
        p = subprocess.Popen(
            cmd,
            cwd=WORKDIR,
            creationflags=CREATE_NEW_CONSOLE
        )
        processes.append(p)

    print("Processes started.")


async def main():
    nc = await nats.connect(NATS_SERVER)

    async def message_handler(msg):
        try:
            text = msg.data.decode("utf-8")
            data = json.loads(text)
        except Exception as e:
            print("Invalid message:", e)
            print(msg.data)
            return

        print("Received:", data)

        if data.get("ready") is True:
            start_processes()

    await nc.subscribe(SUBJECT, cb=message_handler)

    print(f"Listening NATS subject: {SUBJECT}")
    print(f"NATS server: {NATS_SERVER}")

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())