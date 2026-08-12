import asyncio
import contextlib
import json
import os
import sys
import unittest

from nats import connect
from nats.aio.client import Client


class TestClockworkE2E(unittest.IsolatedAsyncioTestCase):
    """End-to-end integration tests for Clockwork control engine."""

    async def asyncSetUp(self) -> None:
        """Set up test-wide variables and NATS connection."""
        self.process: asyncio.subprocess.Process | None = None
        self.nc: Client
        self.nats_url = os.getenv("NATS_URL", "nats://localhost:4222")

        try:
            self.nc = await connect(self.nats_url)
        except Exception as e:
            self.fail(f"Could not connect to NATS at {self.nats_url}: {e}")

    async def asyncTearDown(self) -> None:
        """Ensure subprocesses and NATS connection are cleaned up after every test."""
        if self.nc and self.nc.is_connected:
            await self.nc.close()

        if self.process and self.process.returncode is None:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except (TimeoutError, ProcessLookupError):
                with contextlib.suppress(ProcessLookupError):
                    self.process.kill()
                    await self.process.wait()

    async def _start_clockwork_and_wait_ready(self) -> None:
        """Spawn the Clockwork process and wait for 'started' signal."""
        status_sub = await self.nc.subscribe("clockwork.status")

        cmd = [
            sys.executable,
            "-m",
            "services.control_engine.src.clockwork",
            "--conf-file",
            "./configuration/clockwork.yaml",
        ]

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            async with asyncio.timeout(5.0):
                while True:
                    msg = await status_sub.next_msg(timeout=None)
                    if msg.data.decode().strip() == "started":
                        break
        except TimeoutError:
            self.fail(
                "Timed out after 5 s waiting for Clockwork to start",
            )
        finally:
            await status_sub.unsubscribe()

    async def test_control_emits_required_states(self) -> None:
        """Control test: Verify Clockwork emits expected signal states after start."""
        states_received_future: asyncio.Future[set[str]] = (
            asyncio.get_running_loop().create_future()
        )
        expected_states = {"b", "5", "<"}
        seen_states: set[str] = set()

        async def message_handler(msg) -> None:
            if states_received_future.done():
                return

            with contextlib.suppress(json.JSONDecodeError):
                payload = json.loads(msg.data.decode("utf-8"))
                if isinstance(payload, dict):
                    substate = payload.get("substate")
                    if substate in expected_states:
                        seen_states.add(substate)

                    if seen_states == expected_states:
                        states_received_future.set_result(seen_states)

        subject = "group.control.j1.*"
        control_sub = await self.nc.subscribe(subject, cb=message_handler)

        await self._start_clockwork_and_wait_ready()

        # Command Clockwork to begin updating
        await self.nc.publish("clockwork.command", b"start")

        timeout_seconds = 10.0
        try:
            matched_states = await asyncio.wait_for(
                states_received_future,
                timeout=timeout_seconds,
            )
            self.assertEqual(matched_states, expected_states)
        except TimeoutError:
            self.fail(
                f"Timed out after {timeout_seconds} s waiting for states "
                f"{expected_states} on subject '{subject}'. Saw: {seen_states}",
            )
        finally:
            await control_sub.unsubscribe()

    async def test_command_start_and_stop_transitions(self) -> None:
        """Command test: Verify Clockwork responds to start and stop commands."""
        await self._start_clockwork_and_wait_ready()

        # Initial state should be idling
        status_res = await self.nc.request("clockwork.status", timeout=2.0)
        self.assertEqual(status_res.data.decode().strip(), "idling")

        # Send start command -> status should transition to updating
        await self.nc.publish("clockwork.command", b"start")
        status_res = await self.nc.request("clockwork.status", timeout=2.0)
        self.assertEqual(status_res.data.decode().strip(), "updating")

        # Send stop command -> status should transition back to idling
        await self.nc.publish("clockwork.command", b"stop")
        status_res = await self.nc.request("clockwork.status", timeout=2.0)
        self.assertEqual(status_res.data.decode().strip(), "idling")

        # Send start command again -> status should transition back to updating
        await self.nc.publish("clockwork.command", b"start")
        status_res = await self.nc.request("clockwork.status", timeout=2.0)
        self.assertEqual(status_res.data.decode().strip(), "updating")


if __name__ == "__main__":
    unittest.main()
