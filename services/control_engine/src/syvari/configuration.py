from typing import Any


class SyvariControllerConfiguration:
    """
    Configuration object for SYVARI signal controller.
    """

    def __init__(self, controller_configuration: dict[str, Any]) -> None:
        self.name = controller_configuration["name"]
        self.sumo_name = controller_configuration["sumo_name"]

        # This is a list of group names used to assign an index to all groups.
        groups_order: list[str] = controller_configuration["group_list"]
        # This is a phase count * group count matrix of 0 and 1 depending on if group is green or not in a phase.
        phases_matrix: list[list[int]] = controller_configuration["phases"]
        # Group count * group count matrix of intergreen times between groups.
        intergreen_matrix: list[list[float]] = controller_configuration["intergreens"]

        # Safety check for conflicting phases
        if _contains_conflicting_phase(phases_matrix, intergreen_matrix):
            raise ValueError("Configured phases contain conflicts")

        # Convert the phase matrix to a matrix of active group names.
        # Group names are easier to handle later.
        self.phases = _get_active_groups_by_phase(groups_order, phases_matrix)

        self.group_confs: list[SyvariGroupConfiguration] = []

        det_confs_by_group = _get_detector_configurations_by_group(
            controller_configuration["detectors"]
        )

        i: int = 0
        for signal_group in controller_configuration["signal_groups"]:
            name: str = signal_group["name"]
            sync_start: float = signal_group["sync_start"]
            sync_end: float = signal_group["sync_end"]
            min_green: float = signal_group["min_green"]
            min_guaranteed: float = signal_group["min_guaranteed"]

            # Get the names of conflicting groups based on intergreens for the target group
            conflict_groups = _get_conflicting_groups(
                groups_order, intergreen_matrix[i]
            )

            group_conf = SyvariGroupConfiguration(
                name,
                conflict_groups,
                sync_start,
                sync_end,
                min_green,
                min_guaranteed,
                det_confs_by_group[name],
            )

            self.group_confs.append(group_conf)
            i += 1


def _contains_conflicting_phase(
    phases: list[list[int]], intergreens: list[list[float]]
) -> bool:
    for phase in phases:
        for i in range(len(phase)):
            # Only check active groups
            if phase[i] == 0:
                continue

            # Check all intergreens for the group
            for j in range(len(intergreens[i])):
                # Skip non-conflicting groups
                if intergreens[i][j] == 0:
                    continue

                # If conflicting group is active in the same phase, we have a conflict in the phase
                if phase[j] != 0:
                    return True

    return False


def _get_conflicting_groups(
    groups: list[str], group_intergreens: list[float]
) -> list[str]:
    conflict_groups: list[str] = []
    for i in range(len(groups)):
        if group_intergreens[i] != 0:
            conflict_groups.append(groups[i])

    return conflict_groups


def _get_active_groups_by_phase(
    groups_order: list[str], phase_matrix: list[list[int]]
) -> list[list[str]]:
    """
    Maps a binary phase matrix to a list of active signal group names per phase.

    Args:
        groups_order: List of signal group names in column order.
        phase_matrix: A 2D grid of 0s and 1s, where rows represent phases
                      and columns represent signal groups.

    Returns:
        A list of lists, where each sublist contains the names of the
        signal groups active during that phase.
    """
    active_groups_per_phase: list[list[str]] = []

    for i in range(len(phase_matrix)):
        phase_active_groups: list[str] = []

        for j in range(len(phase_matrix[i])):
            if phase_matrix[i][j] == 1:
                group_name: str = groups_order[j]
                phase_active_groups.append(group_name)

        active_groups_per_phase.append(phase_active_groups)

    return active_groups_per_phase


def _get_detector_configurations_by_group(
    detector_configurations: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """
    Converts detector configurations to a dictionary of with signal group name as the key.
    This makes it easy to get detectors for a specific signal group.

    Args:
        detector_configurations: Detector configuration dictionary read from controller configuration JSON.

    Returns:
        Dictionary with mappings from signal group name to a dictionary of detector configurations.
    """

    detector_confs_by_group: dict[str, dict[str, Any]] = {}

    for det_name, det_data in detector_configurations.items():
        groups: list[str] = []

        single_group = det_data.get("group")
        if single_group:
            groups.append(single_group)

        request_groups = det_data.get("request_groups")
        if request_groups:
            groups.extend(request_groups)

        for group in groups:
            if group not in detector_confs_by_group:
                detector_confs_by_group[group] = {}

            detector_confs_by_group[group][det_name] = det_data

    return detector_confs_by_group


class SyvariGroupConfiguration:
    """
    Configuration object for SYVARI signal group.
    """

    def __init__(
        self,
        name: str,
        conflict_group_names: list[str],
        sync_start: float,
        sync_end: float,
        min_green: float,
        min_guaranteed: float,
        detector_confs: dict[str, Any],
        priority_max: float | None = None,
    ) -> None:
        self.name = name
        self.conflict_groups = conflict_group_names
        self.sync_start = sync_start
        self.sync_end = sync_end
        self.min_green = min_green
        self.min_guaranteed = min_guaranteed
        self.detector_confs = detector_confs
        self.priority_max = priority_max


# ==========================================
# AI generated unit tests for the module.
# Run tests by running the file.
# ==========================================

import unittest


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
        """Test that passes valid detector configurations to function."""
        detector_confs: dict[str, Any] = {
            "det_1": {  # Simple loop detector for three signal groups
                "type": "request",
                "sumo_id": "abc",
                "request_groups": ["group_1", "group_2"],
            },
            "det_2": {  # e3 detector for existing group
                "type": "e3detector",
                "sumo_id": "def",
                "group": "group_1",
            },
            "det_3": {  # e3 detector for a new group
                "type": "e3detector",
                "sumo_id": "def",
                "group": "group_3",
            },
        }

        expected: dict[str, dict[str, Any]] = {
            "group_1": {  # Group with 2 detectors
                "det_1": {
                    "type": "request",
                    "sumo_id": "abc",
                    "request_groups": ["group_1", "group_2"],
                },
                "det_2": {
                    "type": "e3detector",
                    "sumo_id": "def",
                    "group": "group_1",
                },
            },
            "group_2": {  # Group with one detector
                "det_1": {
                    "type": "request",
                    "sumo_id": "abc",
                    "request_groups": ["group_1", "group_2"],
                },
            },
            "group_3": {  # Group with one detector
                "det_3": {
                    "type": "e3detector",
                    "sumo_id": "def",
                    "group": "group_3",
                },
            },
        }

        result = _get_detector_configurations_by_group(detector_confs)
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
