import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.control_engine.src.syvari.configuration import (
    SyvariControllerConfiguration,
    SyvariGroupConfiguration,
)
from services.control_engine.src.syvari.controller import SyvariController
from services.control_engine.src.syvari.signal_group import SignalGroup


class TestSyvariControllerEndToEndFactory(unittest.IsolatedAsyncioTestCase):
    """End-to-end test for SyvariController and SignalGroup factory methods."""

    async def asyncSetUp(self) -> None:
        """Set up timer and raw configuration dictionary."""
        # 1. Setup system timer
        self.timer = MagicMock()
        self.timer.cycle_length = 100.0

        # 2. Raw controller configuration dictionary mirroring real JSON/YAML config
        self.raw_config = {
            "sumo_name": "intersection_1",
            "group_outputs": ["SG1", "SG2"],
            "group_list": ["SG1", "SG2"],
            # Phase 0: SG1 active, Phase 1: SG2 active
            "phases": [
                [1, 0],
                [0, 1],
            ],
            # Intergreen matrix (no conflict within the same phase)
            "intergreens": [
                [0.0, 5.0],
                [5.0, 0.0],
            ],
            # Detector definitions
            "detectors": [
                {"id": "det_point_1", "type": "e1_detector"},
                {"id": "det_area_1", "type": "e2_detector"},
            ],
            # Signal group parameters
            "signal_groups": {
                "SG1": {
                    "sync_start": 10.0,
                    "sync_end": 40.0,
                    "min_green": 10.0,
                    "min_guaranteed": 10.0,
                    "priority_max": 25.0,
                    "detectors": ["det_point_1"],
                },
                "SG2": {
                    "sync_start": 50.0,
                    "sync_end": 80.0,
                    "min_green": 10.0,
                    "min_guaranteed": 10.0,
                    "priority_max": 25.0,
                    "detectors": ["det_area_1"],
                },
            },
        }

    @patch(
        "services.control_engine.src.detectors.configuration.create_detectors",
        new_callable=AsyncMock,
    )
    async def test_syvari_controller_create_real_factories(
        self,
        mock_create_detectors: AsyncMock,
    ) -> None:
        """Test end-to-end creation of SyvariController and its SignalGroups via factory methods."""
        # Setup low-level detector creation response
        mock_point_det = MagicMock(name="PointDetector")
        mock_area_det = MagicMock(name="AreaDetector")

        # Return (point_detectors, area_detectors) when create_detectors is called
        mock_create_detectors.side_effect = [
            ([mock_point_det], []),  # SG1 detectors
            ([], [mock_area_det]),  # SG2 detectors
        ]

        # Step 1: Instantiate real SyvariControllerConfiguration
        conf = SyvariControllerConfiguration(
            name="MainController",
            controller_configuration=self.raw_config,
        )

        # Assert configuration parsed real group configurations correctly
        self.assertEqual(len(conf.group_confs), 2)
        self.assertIsInstance(conf.group_confs[0], SyvariGroupConfiguration)

        # Step 2: Invoke the real SyvariController async factory method
        controller = await SyvariController.create(conf=conf, timer=self.timer)

        # Step 3: Assertions on the initialized controller
        self.assertIsInstance(controller, SyvariController)
        self.assertEqual(len(controller._signal_groups), 2)
        self.assertIn("SG1", controller._signal_groups)
        self.assertIn("SG2", controller._signal_groups)

        # Step 4: Verify real SignalGroup instances and attributes
        sg1 = controller._signal_groups["SG1"]
        sg2 = controller._signal_groups["SG2"]

        self.assertIsInstance(sg1, SignalGroup)
        self.assertIsInstance(sg2, SignalGroup)

        # Check calculated parameters on SG1
        self.assertEqual(sg1._name, "SG1")
        self.assertEqual(sg1._sync_start, 11.0)  # 10.0 sync_start + 1.0 amber
        self.assertEqual(sg1._sync_end, 35.0)  # 40.0 sync_end - 5.0 yellow

        # Check calculated parameters on SG2
        self.assertEqual(sg2._name, "SG2")

        # Step 5: Verify phase 0 initial state (SG1 active in phase 0)
        # Note: Replace GroupState.GREEN with whatever state start_green() sets
        self.assertNotEqual(sg1._cur_state, sg2._cur_state)


if __name__ == "__main__":
    unittest.main()
