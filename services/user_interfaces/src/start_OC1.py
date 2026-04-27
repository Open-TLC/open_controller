import subprocess
import sys
import time

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

cmd3 = [sys.executable,
        "services/indicators/src/traffic_indicators.py",
        "--nats-server", "10.8.0.36",
        "--conf", "models/JS_266_DEMO/ind/JS_266-267_live_radars.json"
        ]

CREATE_NEW_CONSOLE = subprocess.CREATE_NEW_CONSOLE

p1 = subprocess.Popen(
    cmd1,
    cwd=r"C:\DEVE\open_controller",
    creationflags=CREATE_NEW_CONSOLE
)

p2 = subprocess.Popen(
    cmd2,
    cwd=r"C:\DEVE\open_controller",
    creationflags=CREATE_NEW_CONSOLE
)


p3 = subprocess.Popen(
    cmd3,
    cwd=r"C:\DEVE\open_controller",
    creationflags=CREATE_NEW_CONSOLE
)

print("Programs started")


count = 0
while True:
  time.sleep(100)
  count +=1


