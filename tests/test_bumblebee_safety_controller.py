import unittest

import numpy as np

from services.control_engine.src.bumblebee.safety_controller import SafetyController
from services.control_engine.src.geometry.junction_geometry import JunctionGeometry


class TestSafetyController(unittest.TestCase):
    """Unit tests for Bumblebee's safety controller."""

    def test_asymmetric_clearance_transitions(self) -> None:
        """Test asymmetric intergreens between vehicle and pedestrian groups.

        - Pedestrian -> Vehicle needs a 10s lockout.
        - Vehicle -> Pedestrian needs a 1s lockout.
        """
        raw_conf = {
            "links": {
                "0": ["1a"],
            },
            "crossings": {
                "P1": ["0"],
            },
        }
        geometry = JunctionGeometry("j1", raw_conf)
        intergreens = np.array(
            [
                [0.0, 1.0],
                [10.0, 0.0],
            ],
        )

        controller = SafetyController(
            intergreens,
            geometry,
            step_length=1.0,
            default_yellow=3.0,
        )

        # Phases mapping check:
        # Index 0: [0, 1] (Pedestrian Green)
        # Index 1: [1, 0] (Vehicle Green)
        np.testing.assert_array_equal(controller._phases[0], [0, 1])
        np.testing.assert_array_equal(controller._phases[1], [1, 0])

        # --- Test 1: Pedestrian -> Vehicle (Needs 10s clearance) ---
        # Initialize controller to Pedestrian Green state
        controller._current_states = ["r", "g"]

        # Step 0: Command transition to vehicle green (Phase 1: [1, 0]).
        # Pedestrian node transitions g -> y. Lockout on vehicle node set to 10s.
        # Timer ticks immediately down by 1s.
        state = controller.step(1)
        self.assertEqual(state, "ry")
        self.assertEqual(controller._yellow_timers[1], 2.0)
        self.assertEqual(controller._lockout_timers[0], 9.0)

        # Step 1: Tick (1s remaining on yellow, 8s on lockout).
        state = controller.step(1)
        self.assertEqual(state, "ry")

        # Step 2: Tick (0s remaining on yellow, 7s on lockout).
        state = controller.step(1)
        self.assertEqual(state, "ry")

        # Steps 3 through 8: Tick until the 10s lockout is exhausted.
        for _ in range(7):
            state = controller.step(1)
            self.assertEqual(state, "rr")

        # Step 9: Lockout ticks down from 1s to 0s. Vehicle is finally allowed green!
        state = controller.step(1)
        self.assertEqual(state, "gr")

        # --- Test 2: Vehicle -> Pedestrian (Needs 1s clearance) ---
        # Stabilize at vehicle green: state is "gr"
        self.assertEqual(controller._current_states, ["g", "r"])

        # Step 0: Command transition back to pedestrian green (Phase 0: [0, 1]).
        # Vehicle goes g -> y. Lockout on pedestrian set to 1s.
        # Lockout immediately ticks down to 0s at the end of the step.
        state = controller.step(0)
        self.assertEqual(state, "yr")
        self.assertEqual(controller._yellow_timers[0], 2.0)
        self.assertEqual(controller._lockout_timers[1], 0.0)

        # Step 1: Yellow 1s, lockout 0s
        state = controller.step(0)
        self.assertEqual(state, "yr")

        # Step 2: Yellow 0s, lockout 0s
        state = controller.step(0)
        self.assertEqual(state, "yr")

        # Step 3: Yellow ended, pedestrian transitions to green.
        state = controller.step(0)
        self.assertEqual(state, "rg")

    def test_lockout_timer_precedence_is_max(self) -> None:
        """Test green transition requires all conflicting lockouts to be 0."""
        # Links 0 and 1 do not conflict with each other.
        # Crossing P1 (index 2) spans both links, so it conflicts with both.
        raw_conf = {
            "links": {
                "0": ["1a"],
                "1": ["2a"],
            },
            "crossings": {
                "P1": ["0", "1"],
            },
        }
        geometry = JunctionGeometry("j1", raw_conf)

        # Nodes 0 and 1 transition to red simultaneously.
        # Node 2 (P1) wants to go green.
        # Node 0 -> Node 2 requires 4.0s
        # Node 1 -> Node 2 requires 2.0s
        intergreens = np.array(
            [
                [0.0, 0.0, 4.0],
                [0.0, 0.0, 2.0],
                [0.0, 0.0, 0.0],
            ],
        )

        controller = SafetyController(
            intergreens,
            geometry,
            step_length=1.0,
            default_yellow=3.0,
        )

        controller._current_states = ["g", "g", "r"]

        # Step 0: Transition to Phase 0 (Node 2 Green: [0, 0, 1])
        controller.step(0)
        self.assertEqual(
            controller._lockout_timers[2],
            3.0,
        )  # 4.0s max lockout initialized, ticked down by 1.0s step

    def test_fractional_step_durations(self) -> None:
        """Test timing logic with fractional simulation steps (0.5s)."""
        raw_conf = {
            "links": {
                "0": ["0a"],
                "1": ["0a"],
            },
        }
        geometry = JunctionGeometry("j1", raw_conf)

        intergreens = np.array(
            [
                [0.0, 2.0],
                [2.0, 0.0],
            ],
        )
        controller = SafetyController(
            intergreens,
            geometry,
            step_length=0.5,
            default_yellow=1.5,
        )

        controller._current_states = ["g", "r"]

        expected_states = [
            "yr",  # step 1: yellow=1.5, lockout=2.0
            "yr",  # step 2: yellow=1.0, lockout=1.5
            "yr",  # step 3: yellow=0.5, lockout=1.0
            "rr",  # step 4: yellow=0.0, lockout=0.5 (yellow expired, lockout > 0)
            "rg",  # step 5: lockout expired -> node 1 transitions to green
        ]

        for expected_state in expected_states:
            state = controller.step(0)
            self.assertEqual(state, expected_state)


if __name__ == "__main__":
    unittest.main()
