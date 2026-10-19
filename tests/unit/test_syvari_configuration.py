import unittest
from typing import Any

from services.control_engine.src.syvari.configuration import (
    _contains_conflicting_phase,
    _get_active_groups_by_phase,
    _get_conflicting_groups,
    _get_detector_configurations_by_group,
)


class TestSyvariConfiguration(unittest.TestCase):
    # ==========================================
    # Tests for contains_conflicting_phase
    # ==========================================

    def test_contains_conflicting_phase_no_conflict(self):
        """Test a phase matrix where active groups do not conflict with each other."""
        # 3 groups. Phase 1 activates group 0 and 1. Phase 2 activates group 2.
        phases = [
            [1, 1, 0],  # Phase 1: Group 0 and 1 active
            [0, 0, 1],  # Phase 2: Group 2 active
        ]
        # Intergreens matrix: Group 0 conflicts with 2. Group 1 conflicts with 2.
        # Group 0 and 1 do NOT conflict with each other.
        intergreens = [
            [0.0, 0.0, 5.0],  # Group 0 conflicts with 2 (5s intergreen)
            [0.0, 0.0, 4.0],  # Group 1 conflicts with 2 (4s intergreen)
            [5.0, 4.0, 0.0],  # Group 2 conflicts with 0 and 1
        ]
        self.assertFalse(_contains_conflicting_phase(phases, intergreens))

    def test_contains_conflicting_phase_with_conflict(self):
        """Test a phase matrix where a single phase turns on two conflicting groups."""
        # Phase 1 turns on groups 0, 1, and 2 simultaneously
        phases = [[1, 1, 1]]
        # Group 0 conflicts with Group 2 (intergreen = 6.0)
        intergreens = [[0.0, 0.0, 6.0], [0.0, 0.0, 0.0], [6.0, 0.0, 0.0]]
        self.assertTrue(_contains_conflicting_phase(phases, intergreens))

    def test_contains_conflicting_phase_all_inactive(self):
        """Test when phases are entirely inactive (all 0s). Should never trigger a conflict."""
        phases = [[0, 0, 0], [0, 0, 0]]
        # Heavy conflicts exist in the matrix, but nobody is active
        intergreens = [[0.0, 5.0, 5.0], [5.0, 0.0, 5.0], [5.0, 5.0, 0.0]]
        self.assertFalse(_contains_conflicting_phase(phases, intergreens))

    def test_contains_conflicting_phase_empty(self):
        """An empty phase list should evaluate to False."""
        phases: list[list[int]] = []
        intergreens: list[list[float]] = []
        self.assertFalse(_contains_conflicting_phase(phases, intergreens))

    # ==========================================
    # Tests for get_conflicting_groups
    # ==========================================

    def test_get_conflicting_groups_some_conflicts(self):
        """Standard test where some groups have a non-zero intergreen value."""
        groups = ["G1", "G2", "G3", "G4"]
        # Intergreens from the perspective of a specific source group
        group_intergreens = [0.0, 4.5, 0.0, 6.0]

        expected = ["G2", "G4"]
        result = _get_conflicting_groups(groups, group_intergreens)
        self.assertEqual(result, expected)

    def test_get_conflicting_groups_no_conflicts(self):
        """Test when there are no conflicting groups (all intergreens are 0.0)."""
        groups = ["G1", "G2", "G3"]
        group_intergreens = [0.0, 0.0, 0.0]

        expected = []
        result = _get_conflicting_groups(groups, group_intergreens)
        self.assertEqual(result, expected)

    def test_get_conflicting_groups_all_conflict(self):
        """Test when every single listed group conflicts."""
        groups = ["G1", "G2"]
        group_intergreens = [3.0, 4.0]

        expected = ["G1", "G2"]
        result = _get_conflicting_groups(groups, group_intergreens)
        self.assertEqual(result, expected)

    def test_get_conflicting_groups_empty(self):
        """Test behavior with empty inputs."""
        groups: list[str] = []
        group_intergreens: list[float] = []

        expected = []
        result = _get_conflicting_groups(groups, group_intergreens)
        self.assertEqual(result, expected)

    # ==========================================
    # Tests for get_active_groups_by_phase
    # ==========================================

    def setUp(self) -> None:
        """Set up a standard order of signal groups for the intersection."""
        # Typically, numbers represent vehicle directions, letters represent pedestrians
        self.groups_order = ["G1", "G2", "G3", "G4", "P1", "P2"]

    def test_standard_phase_mapping(self):
        """Test mapping a normal binary matrix to their descriptive names."""
        # Row 0: G1, G2, and P1 are active
        # Row 1: G3, G4, and P2 are active
        phase_matrix = [[1, 1, 0, 0, 1, 0], [0, 0, 1, 1, 0, 1]]

        expected = [["G1", "G2", "P1"], ["G3", "G4", "P2"]]

        result = _get_active_groups_by_phase(self.groups_order, phase_matrix)
        self.assertEqual(result, expected)

    def test_all_groups_active(self):
        """Test behavior when a phase activates every single signal group simultaneously."""
        phase_matrix = [[1, 1, 1, 1, 1, 1]]

        expected = [["G1", "G2", "G3", "G4", "P1", "P2"]]

        result = _get_active_groups_by_phase(self.groups_order, phase_matrix)
        self.assertEqual(result, expected)

    def test_all_groups_inactive(self):
        """Test a phase row with entirely 0s (e.g., an all-red clearance buffer phase)."""
        # A matrix where phase 0 has active groups, but phase 1 turns everything off
        phase_matrix = [
            [1, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],  # All red / clearance interval
        ]

        expected: list[list[str]] = [
            ["G1"],
            [],  # Should result in a clean, empty sublist for that phase
        ]

        result = _get_active_groups_by_phase(self.groups_order, phase_matrix)
        self.assertEqual(result, expected)

    def test_single_group_active(self):
        """Test configuration where each phase only runs exactly one group."""
        phase_matrix = [[1, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0], [0, 0, 0, 1, 0, 0]]

        expected = [["G1"], ["G2"], ["G4"]]

        result = _get_active_groups_by_phase(self.groups_order, phase_matrix)
        self.assertEqual(result, expected)

    def test_empty_inputs(self):
        """Test that passing empty configurations gracefully handles the loop and returns empty list."""
        empty_groups: list[str] = []
        empty_matrix: list[list[int]] = []

        result = _get_active_groups_by_phase(empty_groups, empty_matrix)
        self.assertEqual(result, [])

    # ==========================================
    # Tests for get_detector_configurations_by_group
    # ==========================================


def test_valid_detector_confs(self):
    abc_conf = {"type": "e1_detector", "id": "abc"}
    def_conf = {"type": "e2_detector", "id": "def"}
    ghi_conf = {"type": "e3_detector", "id": "ghi"}

    controller_conf: dict[str, Any] = {
        "signal_groups": {
            "group1": {"detectors": ["abc", "def"]},
            "group2": {"detectors": ["ghi", "def"]},
            "group3": {"detectors": ["abc"]},
        },
        "detectors": [abc_conf, def_conf, ghi_conf],
    }

    result = _get_detector_configurations_by_group(controller_conf)

    # Flatten the result down to strings/IDs for comparison
    flattened_result = {
        group: [det.id for det in det_list] for group, det_list in result.items()
    }

    # Define your expected structure based purely on IDs
    expected_ids = {
        "group1": ["abc", "def"],
        "group2": ["ghi", "def"],
        "group3": ["abc"],
    }

    self.assertEqual(flattened_result, expected_ids)
