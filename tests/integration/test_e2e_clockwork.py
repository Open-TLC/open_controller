import asyncio
import contextlib
import json
import os
import sys
import unittest

from nats import connect
from nats.aio.client import Client


class TestClockworkE2E(unittest.IsolatedAsyncioTestCase):
    """Test that Clockwork starts and starts publishing signal states to NATS."""

    async def asyncSetUp(self) -> None:
        """Set up test-wide variables."""
        self.process: asyncio.subprocess.Process | None = None
        self.nc: Client | None = None
        self.nats_url = os.getenv("NATS_URL", "nats://localhost:4222")

    async def asyncTearDown(self) -> None:
        """Ensure subprocesses and connections are cleaned up after every test."""
        if self.nc and self.nc.is_connected:
            await self.nc.close()

        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except (TimeoutError, ProcessLookupError):
                # If it refuses to shut down within 2 seconds, kill it forcefully
                with contextlib.suppress(ProcessLookupError):
                    self.process.kill()
                    await self.process.wait()

    async def test_clockwork_status_emits_required_states(self) -> None:
        """Run Clockwork and assert 'b', '5', and '<' appear in the status."""
        try:
            self.nc = await connect(self.nats_url)
        except Exception as e:
            self.fail(f"Could not connect to NATS at {self.nats_url}: {e}")

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
                substate = payload.get("substate")

                # Track the substate if it's one we care about
                if substate in expected_states:
                    seen_states.add(substate)

                # Complete the test early if all target states have been received
                if seen_states == expected_states and not states_received_future.done():
                    states_received_future.set_result(seen_states)

        # Subscribe to states of signal groups of controller "j1"
        subject = "group.control.j1.*"
        sub = await self.nc.subscribe(subject, cb=message_handler)

        cmd = [
            sys.executable,
            "-m",
            "services.control_engine.src.clockwork",
            "--conf-file",
            "./configuration/clockwork.yaml",
        ]

        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=None,
                stderr=None,
            )
        except FileNotFoundError:
            self.fail("Failed to run Clockwork.")

        timeout_seconds = 10.0
        try:
            matched_states = await asyncio.wait_for(
                states_received_future,
                timeout=timeout_seconds,
            )
        except TimeoutError:
            self.fail(
                f"Timed out after {timeout_seconds}s waiting for states "
                f"{expected_states} on subject '{subject}'. Only saw: {seen_states}",
            )

        await sub.unsubscribe()

        self.assertIn("b", matched_states)
        self.assertIn("5", matched_states)
        self.assertIn("<", matched_states)


if __name__ == "__main__":
    unittest.main()
