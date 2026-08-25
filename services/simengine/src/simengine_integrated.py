"""Integrated simulation environment.

This is a module for running in-process simulations. This is contrary to the
distributed simulation environment, that uses NATS. You should always default to the
distributed system, unless you have a special reason not to.
"""

import asyncio
import time

import libsumo

from services.control_engine.src.configuration import (
    SimEngineConf,
    load_sim_engine_conf_from_file,
    read_command_line,
)
from services.control_engine.src.controller_creation import create_controller
from services.control_engine.src.detectors.area_detector import AreaDetector
from services.control_engine.src.detectors.configuration import create_detectors
from services.control_engine.src.detectors.point_detector import PointDetector
from services.control_engine.src.signal_controller import SignalController
from services.control_engine.src.timer import Timer

from .websumo_interface import WebsumoInterface

SUMO_BIN: str = "sumo"


def main() -> None:
    args = read_command_line()

    conf = load_sim_engine_conf_from_file(args.conf_file)

    simengine = SimEngine(conf)

    simengine.run()


class SimEngine:
    def __init__(
        self,
        conf: SimEngineConf,
    ) -> None:
        self._timer = Timer(conf.timer)
        self._sync_real_time: bool = conf.timer.mode == "real"

        self._start_sumo(conf.sumo_conf_filename, self._timer.step_length)

        nats_conf = {
            "server": "nats",
            "port": 4222,
        }

        self._websumo = WebsumoInterface(
            conf.sumo_conf_filename,
            nats_conf,
            enabled=True,
        )

        # create_detectors is an async function so it must be ran inside the
        # asyncio wrapper.
        self._detectors: tuple[list[PointDetector], list[AreaDetector]] = asyncio.run(
            create_detectors(conf.detectors),
        )

        self._controllers: list[SignalController] = []
        for contr_conf in conf.controllers:
            # Create controller.
            controller = create_controller(contr_conf, self._timer, self._detectors)
            self._controllers.append(controller)

    def _start_sumo(self, filename: str, step_length: float) -> None:
        sumo_args = [
            SUMO_BIN,
            "-c",
            filename,
            "--quit-on-end",
            "--step-length",
            str(step_length),
            "--time-to-teleport",
            "-1",
        ]
        libsumo.start(sumo_args)

    def run(self) -> None:
        try:
            while libsumo.simulation.getMinExpectedNumber() > 0:
                if self._sync_real_time:
                    # Synchronize update cycle to the timer.
                    time.sleep(self._timer.wall_time_to_next_step())

                # Advancing timer.
                self._timer.tick()

                # Update all detectors.
                for detector in self._detectors[0] + self._detectors[1]:
                    detector.tick()

                # Update all controllers and apply their states in SUMO.
                for controller in self._controllers:
                    controller.tick()
                    new_states: str = controller.signal_states_sumo
                    libsumo.trafficlight.setRedYellowGreenState(
                        controller.id,
                        new_states,
                    )

                # Advance simulation.
                libsumo.simulationStep()

                # Publish state to WebSUMO.
                self._websumo.publish_state()
        finally:
            self._websumo.publish_end()
            self._websumo.close()


if __name__ == "__main__":
    main()
