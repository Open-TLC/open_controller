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
                [0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
                [0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 1, 1],
                [0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 1, 1],
                [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1],
                [1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 1],
                [0, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 0],
                [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0],
                [0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1],
                [1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 1, 1],
                [0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
                [0, 1, 1, 0, 0, 1, 1, 1, 1, 0, 0, 0],
                [0, 1, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0],
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


if __name__ == "__main__":
    unittest.main()
