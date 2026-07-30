import unittest

import numpy as np

from services.control_engine.src.geometry.junction_geometry import (
    JunctionGeometry,
)


class TestJunctionGeometry(unittest.TestCase):
    """Unit tests for junction geometry."""

    def test_valid_parsing_and_dimensions(self) -> None:
        """Valid configuration yields conflict matrix of correct shape."""
        raw_conf = {
            "links": {
                "0": ["5a"],
                "1": ["3a"],
            },
            "crossings": {
                "P1": ["1", "2"],
            },
        }
        geo = JunctionGeometry("j1", raw_conf)
        matrix = geo.generate_conflict_matrix()

        self.assertEqual(matrix.shape, (3, 3))

    def test_missing_crossings_graceful_fallback(self) -> None:
        """Junction without pedestrian crossings yields correct conflict values."""
        raw_conf = {
            "links": {
                "0": ["5a"],
                "1": ["3a"],
                "2": ["4a"],
            },
        }
        geo = JunctionGeometry("j1", raw_conf)
        matrix = geo.generate_conflict_matrix()

        self.assertEqual(matrix.shape, (3, 3))
        self.assertTrue(np.all((matrix == 0) | (matrix == 1)))

    def test_empty_configuration(self) -> None:
        """Verify that an empty network configuration results in an empty 0x0 matrix."""
        raw_conf = {
            "links": {},
            "crossings": {},
        }
        geo = JunctionGeometry("j1", raw_conf)
        matrix = geo.generate_conflict_matrix()
        self.assertEqual(matrix.shape, (0, 0))

    def test_invalid_exit_node_raises_value_error(self) -> None:
        """All exit nodes must have an alphabet part."""
        invalid_conf = {
            "links": {
                "0": ["5"],  # '5' lacks an alphabetic lane identifier
            },
        }
        with self.assertRaises(ValueError) as context:
            JunctionGeometry("j1", invalid_conf)
        self.assertIn(
            "All exit nodes must have an alphabet part",
            str(context.exception),
        )

    def test_invalid_node_string_format(self) -> None:
        """Ensure that malformed node IDs cause early failures."""
        bad_confs = [
            {"links": {"-1": ["2a"]}},
            {"links": {"0": ["2A"]}},  # Uppercase not allowed by regex [a-z]*
            {"links": {"one": ["2a"]}},
            {"links": {"1": ["a2"]}},  # Letters must follow numbers
        ]
        for conf in bad_confs:
            with self.subTest(conf=conf), self.assertRaises(ValueError):
                JunctionGeometry("j1", conf)

    def test_self_conflict_always_zero(self) -> None:
        """Safety invariant: An active link or crossing doesn't conflict with itself."""
        raw_conf = {
            "links": {
                "0": ["5a", "4a"],
                "1": ["3a"],
            },
            "crossings": {
                "P1": ["0", "1"],
            },
        }
        geo = JunctionGeometry("j1", raw_conf)
        matrix = geo.generate_conflict_matrix()

        # The diagonal elements of the square matrix must be entirely 0
        diagonal = np.diagonal(matrix)
        np.testing.assert_array_equal(diagonal, np.zeros(len(diagonal), dtype=int))

    def test_vehicle_to_vehicle_diverging(self) -> None:
        """Diverging lanes never conflict."""
        raw_conf = {
            "links": {
                "0": ["3a", "2a", "1a"],
                "1": ["0a", "3a", "2a"],
                "2": ["1a", "0a", "3a"],
                "3": ["2a", "1a", "0a"],
            },
        }
        geo = JunctionGeometry("j1", raw_conf)
        matrix = geo.generate_conflict_matrix()

        expected = np.array(
            [
                [0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1],
                [0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1],
                [0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1],
                [1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1],
                [1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1],
                [1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1],
                [1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1],
                [1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1],
                [1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1],
                [1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0],
                [1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0],
                [1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0],
            ],
        )

        np.testing.assert_array_equal(matrix, expected)

    def test_vehicle_to_vehicle_merge_conflict(self) -> None:
        """Converging vehicle links should have a conflict (1)."""
        raw_conf = {
            "links": {
                "0": ["5a"],
                "1": ["5a"],
            },
        }
        geo = JunctionGeometry("j1", raw_conf)
        matrix = geo.generate_conflict_matrix()

        self.assertEqual(matrix[0, 1], 1)
        self.assertEqual(matrix[1, 0], 1)

    def test_vehicle_to_vehicle_crossing_conflict(self) -> None:
        """Crossing vehicle links should have a conflict (1)."""
        raw_conf = {
            "links": {
                "0": ["3a"],
                "1": ["4a"],
            },
        }
        geo = JunctionGeometry("j1", raw_conf)
        matrix = geo.generate_conflict_matrix()

        self.assertEqual(matrix[0, 1], 1)
        self.assertEqual(matrix[1, 0], 1)

    def test_vehicle_to_vehicle_no_conflict(self) -> None:
        """Parallel vehicle links don't have a conflict (0)."""
        raw_conf = {
            "links": {
                "0": ["1a"],
                "2": ["3a"],
            },
        }
        geo = JunctionGeometry("j1", raw_conf)
        matrix = geo.generate_conflict_matrix()

        self.assertEqual(matrix[0, 1], 0)
        self.assertEqual(matrix[1, 0], 0)

    def test_pedestrian_vehicle_asymmetrical_conflicts(self) -> None:
        """Pedestrian crossings yield correct conflict values.

        - Pedestrian -> Vehicle transition: Must equal 2 (longer clearance)
        - Vehicle -> Pedestrian transition: Must equal 3 (shorter clearance)
        """
        raw_conf = {
            "links": {
                "0": ["5a"],
            },
            "crossings": {
                "P1": ["0", "1"],
            },
        }
        geo = JunctionGeometry("j1", raw_conf)
        matrix = geo.generate_conflict_matrix()

        # Vehicle -> Pedestrian transition (Row 0, Col 1)
        self.assertEqual(matrix[0, 1], 3)

        # Pedestrian -> Vehicle transition (Row 1, Col 0)
        self.assertEqual(matrix[1, 0], 2)

    def test_pedestrian_to_pedestrian_isolation(self) -> None:
        """Pedestrian crossings don't conflict with each other (0)."""
        raw_conf = {
            "links": {
                "0": ["5a"],
            },
            "crossings": {
                "P1": ["0"],
                "P2": ["0"],
            },
        }
        geo = JunctionGeometry("j1", raw_conf)
        matrix = geo.generate_conflict_matrix()

        self.assertEqual(matrix[1, 2], 0)
        self.assertEqual(matrix[2, 1], 0)

    def test_empty_configuration_returns_empty_array(self) -> None:
        """An empty junction configuration yields an empty (0, 0) array."""
        raw_conf = {
            "links": {},
            "crossings": {},
        }
        geo = JunctionGeometry("j1", raw_conf)
        phases = geo.get_possible_phases()

        self.assertEqual(phases.shape, (0, 0))
        self.assertTrue(np.issubdtype(phases.dtype, np.integer))

    def test_single_link_junction(self) -> None:
        """A junction with a single link produces one maximal phase containing that link."""
        raw_conf = {
            "links": {
                "0": ["2a"],
            },
        }
        geo = JunctionGeometry("j1", raw_conf)
        phases = geo.get_possible_phases(min_major_movements=1)

        expected = np.array([[1]])
        np.testing.assert_array_equal(phases, expected)

    def test_non_conflicting_links_combine_into_single_phase(self) -> None:
        """Non-conflicting links should be grouped together into a single all-green phase."""
        raw_conf = {
            "links": {
                "0": ["2a"],  # Parallel flow
                "2": ["0a"],  # Reverse parallel flow
            },
        }
        geo = JunctionGeometry("j1", raw_conf)
        phases = geo.get_possible_phases(min_major_movements=1)

        self.assertEqual(phases.ndim, 2)
        # Verify that both links can be active simultaneously in a maximal phase
        self.assertTrue(np.any(np.all(phases == 1, axis=1)))

    def test_conflicting_links_produce_separate_phases(self) -> None:
        """Crossing/conflicting links cannot be active in the same phase."""
        raw_conf = {
            "links": {
                "0": ["2a"],  # Eastbound through
                "1": ["3a"],  # Northbound through (conflicts with eastbound)
            },
        }
        geo = JunctionGeometry("j1", raw_conf)
        phases = geo.get_possible_phases(min_major_movements=1)

        # Neither phase should have both links active simultaneously
        for phase in phases:
            self.assertFalse(
                phase[0] == 1 and phase[1] == 1,
                "Conflicting links were active at the same time",
            )

    def test_coverage_guarantee_prevents_starvation(self) -> None:
        """Every link and pedestrian crossing must be active in at least one phase.

        Even if an element doesn't meet the `min_major_movements` threshold on its own,
        the fallback mechanism ensures it is included in a fallback phase.
        """
        raw_conf = {
            "links": {
                "0": ["2a"],
                "1": ["3a"],
            },
            "crossings": {
                "P1": ["0", "1"],
            },
        }
        geo = JunctionGeometry("j1", raw_conf)

        # Request higher major movement threshold
        phases = geo.get_possible_phases(min_major_movements=2)

        # Sum down columns: each element (column) must be active (1) in at least 1 phase
        active_counts_per_element = np.sum(phases, axis=0)
        self.assertTrue(
            np.all(active_counts_per_element > 0),
            "At least one link/crossing was left uncovered (starvation risk).",
        )

    def test_varying_min_major_movements_threshold(self) -> None:
        """Increasing min_major_movements restricts phases to those with sufficient major movements."""
        raw_conf = {
            "links": {
                "0": ["2a"],
                "1": ["3a"],
                "2": ["0a"],
            },
            "crossings": {
                "P1": ["0"],
            },
        }
        geo = JunctionGeometry("j1", raw_conf)

        phases_min1 = geo.get_possible_phases(min_major_movements=1)
        phases_min2 = geo.get_possible_phases(min_major_movements=2)

        self.assertIsInstance(phases_min1, np.ndarray)
        self.assertIsInstance(phases_min2, np.ndarray)
        # Higher thresholds filter out smaller candidate phases
        self.assertGreaterEqual(len(phases_min1), len(phases_min2))

    def test_output_array_format_and_uniqueness(self) -> None:
        """Returned array must consist of 0s and 1s, with integer dtype and no duplicate rows."""
        raw_conf = {
            "links": {
                "0": ["2a", "3a"],
                "1": ["3a", "0a"],
            },
            "crossings": {
                "P1": ["0", "1"],
            },
        }
        geo = JunctionGeometry("j1", raw_conf)
        phases = geo.get_possible_phases(min_major_movements=1)

        # Output must be 2D array of integers containing only 0 or 1
        self.assertEqual(phases.ndim, 2)
        self.assertTrue(np.issubdtype(phases.dtype, np.integer))
        self.assertTrue(np.all((phases == 0) | (phases == 1)))

        # Rows must be unique (np.unique should not reduce the row count)
        unique_phases = np.unique(phases, axis=0)
        self.assertEqual(len(phases), len(unique_phases))

    def test_common_junction_phase_generation(self) -> None:
        """Test if common junction geometry generates correct phases."""
        raw_conf = {
            "links": {
                "0": ["4a", "5a"],
                "1": ["2a"],
                "2": ["1a", "4a", "5a"],
                "3": ["1a", "2a"],
                "4": ["5a"],
                "5": ["1a", "2a", "4a"],
            },
        }
        geo = JunctionGeometry("j1", raw_conf)
        phases = geo.get_possible_phases(min_major_movements=2)

        expected_phases = {
            (1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0),  # N-S + S-N through + right
            (0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0),  # N-E + S-W left (Dual left)
            (0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0),  # East all
            (0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1),  # West all
        }

        generated_phase_tuples = {tuple(p) for p in phases}

        for expected in expected_phases:
            self.assertIn(
                expected,
                generated_phase_tuples,
                f"Expected phase {expected} was not found in generated phases.",
            )


if __name__ == "__main__":
    unittest.main()
