import unittest
from unittest.mock import AsyncMock, MagicMock

from services.control_engine.src.detectors.traffic_indicators_area_detector import (
    TrafficIndicatorsAreaDetector,
)


class TestTrafficIndicatorsAreaDetector(unittest.IsolatedAsyncioTestCase):
    """Tests for Traffic Indicators based area detector."""

    async def test_create_detector(self):
        """Test the factory method."""
        mock_nc = AsyncMock()

        detector = await TrafficIndicatorsAreaDetector.create(
            mock_nc,
            "junction_123",
            "group_abc",
        )

        expected_subject = "group.e3.junction_123.group_abc"
        self.assertEqual(mock_nc.subscribe.call_count, 3)
        mock_nc.subscribe.assert_any_call(
            expected_subject,
            cb=detector._update_vehicle_count,  # noqa: SLF001
        )

    async def test_update_vehicle_count_callback(self):
        """Test that the vehicle count callback correctly parses NATS message data."""
        detector = TrafficIndicatorsAreaDetector("j1", "g1")

        # Mock the NATS Msg object and its raw payload bytes
        mock_msg = MagicMock()
        mock_msg.data = b'{"count": 42}'

        # Execute callback manually
        await detector._update_vehicle_count(mock_msg)  # noqa: SLF001

        # Assert internal state updated correctly
        self.assertEqual(detector.vehicle_count, 42.0)

    async def test_update_average_speed_callback(self):
        """Test that the average speed callback correctly calculates averages."""
        detector = TrafficIndicatorsAreaDetector("j1", "g1")

        mock_msg = MagicMock()
        mock_msg.data = b'{"count": 2, "objects": {"car1": {"speed": 10.0}, "car2": {"speed": 20.0}}}'

        await detector._update_average_speed(mock_msg)  # noqa: SLF001

        self.assertEqual(detector.average_speed, 15.0)

    async def test_update_average_speed_empty_payload(self):
        """Test that average speed falls back to 0 if payload has no vehicles."""
        detector = TrafficIndicatorsAreaDetector(junction_id="j1", group_id="g1")

        mock_msg = MagicMock()
        mock_msg.data = b'{"count": 0, "objects": {}}'

        await detector._update_average_speed(mock_msg)  # noqa: SLF001

        self.assertEqual(detector.average_speed, 0.0)


if __name__ == "__main__":
    unittest.main()
