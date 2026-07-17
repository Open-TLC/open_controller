import asyncio
import contextlib
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

    async def test_clockwork_status_emits_b_and_5(self) -> None:
        """Run Clockwork and assert 'b' and '5' appear in the status."""
        try:
            self.nc = await connect(self.nats_url)
        except Exception as e:
            self.fail(f"Could not connect to NATS at {self.nats_url}: {e}")

        message_received_future: asyncio.Future[str] = (
            asyncio.get_running_loop().create_future()
        )

        async def message_handler(msg) -> None:
            payload = msg.data.decode("utf-8")
            if "b" in payload and "5" in payload and not message_received_future.done():
                message_received_future.set_result(payload)

        subject = "clockwork.status.j1"
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
            self.fail("Could not run command. Is Python in your PATH?")

        timeout_seconds = 10.0
        try:
            matched_payload = await asyncio.wait_for(
                message_received_future,
                timeout=timeout_seconds,
            )
        except TimeoutError:
            self.fail(
                f"Timed out after {timeout_seconds}s waiting for a message "
                f"containing 'b' and '5' on subject '{subject}'.",
            )

        await sub.unsubscribe()

        self.assertIn("b", matched_payload)
        self.assertIn("5", matched_payload)


if __name__ == "__main__":
    unittest.main()
