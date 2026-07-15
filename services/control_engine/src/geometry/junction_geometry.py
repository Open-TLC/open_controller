import re
from functools import total_ordering
from typing import Any

import numpy as np


class JunctionGeometry:
    """Junction geometry object.

    This can be used to parse and extract information abou the geometry of a junction.
    """

    def __init__(self, raw_conf: dict[str, Any]) -> None:
        self._conf = raw_conf

        self._links: list[_Link] = []
        self._crossings: list[_Crossing] = []

        for entry_str, exits in raw_conf["links"].items():
            entry_node = _Node(entry_str)
            for exit_str in exits:
                exit_node = _Node(exit_str)
                if exit_node.char == "":
                    raise ValueError(
                        'All exit nodes must have an alphabet part ("2a").',
                    )
                self._links.append(_Link(entry_node, exit_node))

        for crossing_id, crossed_nodes_list in raw_conf.get("crossings", {}).items():
            crossed_nodes = [_Node(node_str) for node_str in crossed_nodes_list]
            self._crossings.append(_Crossing(crossing_id, crossed_nodes))

    def generate_conflict_matrix(self) -> np.ndarray:
        """Generate conflict matrix based on geometry.

        Created matrix has the following values:
            0: No conflict.
            1: Vehicle -> vehicle.
            2: Pedestrian -> vehicle conflict.
            3: Vehicle -> pedestrian conflict.

        """
        all_elements = self._links + self._crossings
        n = len(all_elements)
        conflict_matrix = np.zeros((n, n), dtype=int)

        for i, element_1 in enumerate(all_elements):
            for j, element_2 in enumerate(all_elements):
                # Vehicle link -> conflicting vehicle link.
                if (
                    isinstance(element_1, _Link)
                    and isinstance(element_2, _Link)
                    and element_1.conflicts_with(element_2)
                ):
                    conflict_matrix[i, j] = 1

                # Pedestrian crossing -> conflicting vehicle link.
                # This has a separate value (2), since it requires
                # a longer intergreen time.
                elif (
                    isinstance(element_1, _Crossing)
                    and isinstance(element_2, _Link)
                    and element_1.conflicts_with_link(element_2)
                ):
                    conflict_matrix[i, j] = 2

                # Vehicle link -> conflicting pedestrian crossing.
                # This has a separate value (3), since it requires
                # a shorter intergreen time.
                elif (
                    isinstance(element_1, _Link)
                    and isinstance(element_2, _Crossing)
                    and element_2.conflicts_with_link(element_1)
                ):
                    conflict_matrix[i, j] = 3

        return conflict_matrix


@total_ordering
class _Node:
    def __init__(self, node_id: str):
        # Split ID to number and character parts.
        match = re.match(r"^(\d+)([a-z]*)$", node_id)
        if not match:
            raise ValueError(
                f"Invalid node identifier: '{node_id}'. Must be a "
                "number followed by optional lowercase letters.",
            )

        self.num = int(match.group(1))
        self.char = match.group(2)  # Extracted character, or "" if doesn't exist.

    def _as_tuple(self):
        return (self.num, self.char)

    def __lt__(self, other):
        """Compare nodes."""
        if not isinstance(other, _Node):
            return NotImplemented
        return self._as_tuple() < other._as_tuple()

    def __eq__(self, other):
        """Check equality between nodes."""
        if not isinstance(other, _Node):
            return NotImplemented
        return self._as_tuple() == other._as_tuple()

    def __repr__(self):
        return f"{self.num}{self.char}"

    def __hash__(self):
        return hash(self._as_tuple())


class _Link:
    def __init__(self, start: _Node, end: _Node):
        self.start = start
        self.end = end

    def __eq__(self, other):
        """Check equality between links."""
        if not isinstance(other, _Link):
            return NotImplemented
        return self.start == other.start and self.end == other.end

    def __hash__(self):
        return hash((self.start, self.end))

    def __repr__(self):
        return f"{self.start}->{self.end}"

    @staticmethod
    def _is_between(start: _Node, end: _Node, target: _Node) -> bool:
        """Check if target node is between start and end."""
        if target in (start, end):
            return False
        if start < end:
            return start < target < end
        return target > start or target < end

    def conflicts_with(self, other: "_Link") -> bool:
        """Check if links have a conflict.

        Conflict can be either merge conflict or crossing conflict.

        Args:
            other: Link to be compared with.

        Returns:
            True if links conflict, else if there is no conflict.

        """
        # Link doesn't conflict with itself.
        if self == other:
            return False

        # Merge conflict: Links end on the same node.
        if self.end == other.end and self.start != other.start:
            return True

        # Crossing conflict: Links cross paths.
        # Link 2 crosses link 1 if it starts between link 1's end points AND doesn't
        # end between link 1's end points.
        other_start_inside = self._is_between(self.start, self.end, other.start)
        other_end_inside = self._is_between(self.start, self.end, other.end)

        return other_start_inside != other_end_inside


class _Crossing:
    """Represents a pedestrian crossing."""

    def __init__(self, crossing_id: str, crossed_nodes: list[_Node]):
        self.id = crossing_id
        self.crossed_nodes = set(crossed_nodes)

    def conflicts_with_link(self, link: _Link) -> bool:
        """Check if crossing conflicts with a link.

        Conflict can occur in links start or end node.
        """
        return link.start in self.crossed_nodes or link.end in self.crossed_nodes

    def __eq__(self, other):
        if not isinstance(other, _Crossing):
            return NotImplemented
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"Crossing({self.id})"
