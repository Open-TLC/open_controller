import asyncio
import json
import subprocess
import sys
import nats

NATS_SERVER = "nats://10.8.0.204:4222"
SUBJECT = "oc.status.266"
WORKDIR = r"C:\DEVE\open_controller"

CREATE_NEW_CONSOLE = subprocess.CREATE_NEW_CONSOLE

cmds = [
    
    [
        sys.executable,
        "C:/DEVE/open_controller/services/control_engine/src/clockwork.py",
        "--nats-server", "10.8.0.204",
        "--conf-file=models/JS_266_DEMO/contr/JS1_266_DEMO_042026IG.json"
    ],
    [
        sys.executable,
        "C:/DEVE/open_controller/services/indicators/src/traffic_indicators.py",
        "--nats-server", "10.8.0.204",
        "--conf", "models/JS_266_DEMO/ind/JS_266-267_live_radars.json"
    ]
]

processes = []
started = False


def start_processes():
    global started

    if started:
        print("Already running.")
        return

    print("Starting processes...")
    for cmd in cmds:
        p = subprocess.Popen(
            cmd,
            cwd=WORKDIR,
            creationflags=CREATE_NEW_CONSOLE
        )
        processes.append(p)

    started = True
    print("Processes started.")


def stop_processes():
    global started

    if not started:
        print("Processes already stopped.")
        return

    print("Stopping processes...")

    # First try graceful shutdown
    for p in processes:
        if p.poll() is None:
            print(f"Terminating PID {p.pid}")
            p.terminate()

    # Give them time to exit
    import time
    time.sleep(3)

    # Force kill if still alive
    for p in processes:
        if p.poll() is None:
            print(f"Killing PID {p.pid}")
            p.kill()

    processes.clear()
    started = False

    print("Processes stopped.")


async def main():
    nc = await nats.connect(NATS_SERVER)

    async def message_handler(msg):
        try:
            data = json.loads(msg.data.decode())
        except Exception as e:
            print("Invalid JSON:", e)
            return

        print("Received:", data)

        ready = data.get("ready")

        if ready is True:
            start_processes()

        elif ready is False:
            stop_processes()

    await nc.subscribe(SUBJECT, cb=message_handler)

    print(f"Listening on {SUBJECT}")

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())