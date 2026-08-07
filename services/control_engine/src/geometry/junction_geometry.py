import re
from functools import total_ordering
from typing import Any

import numpy as np


class JunctionGeometry:
    """Junction geometry object.

    This can be used to parse and extract information abou the geometry of a junction.
    """

    def __init__(self, junction_id: str, raw_options: dict[str, Any]) -> None:
        self._conf = raw_options
        self._junction_id = junction_id

        self._links: list[_Link] = []
        self._crossings: list[_Crossing] = []

        # Find the largest node number.
        max_node_num: int = 0

        for entry_str, exits in raw_options["links"].items():
            max_node_num = max(max_node_num, _Node(entry_str).num)
            for exit_str in exits:
                max_node_num = max(max_node_num, _Node(exit_str).num)

        # Build links.
        for entry_str, exits in raw_options["links"].items():
            entry_node = _Node(entry_str)
            for exit_str in exits:
                exit_node = _Node(exit_str)
                if exit_node.char == "":
                    raise ValueError(
                        'All exit nodes must have an alphabet part ("2a").',
                    )
                link = _Link(entry_node, exit_node, max_node_num)
                self._links.append(link)

        for crossing_id, crossed_nodes_list in raw_options.get("crossings", {}).items():
            crossed_nodes = [_Node(node_str) for node_str in crossed_nodes_list]
            self._crossings.append(_Crossing(crossing_id, crossed_nodes))

        # Gather all entry nodes.
        entry_node_ids: list[str] = []
        for link in self._links:
            entry_id = f"{self._junction_id}.{link.start.num}"
            entry_node_ids.append(entry_id)

        # This removes duplicates, though there shouldn't be any.
        self._entry_node_ids: list[str] = list(dict.fromkeys(entry_node_ids))

        # Gather all exit nodes per entry node.
        exit_node_ids: dict[str, list[str]] = {}
        for entry_id in self._entry_node_ids:
            exit_node_ids[entry_id] = []
            for link in self._links:
                if f"{self._junction_id}.{link.start.num}" != entry_id:
                    continue

                exit_id = f"{self._junction_id}.{link.end.num}{link.end.char}"
                exit_node_ids[entry_id].append(exit_id)

        self._exit_node_ids: dict[str, list[str]] = exit_node_ids

        self._num_entry_lanes = len(self._entry_node_ids)

        # Mapping matrix to convert phases from link wise to lane wise.
        self._link_to_lane_map: np.ndarray | None = None

        # Entry IDs of links receiving transit vehicles.
        self._transit_links: list[str] = [
            str(link_id) for link_id in raw_options.get("transit_links", [])
        ]

        # Mapping matrix to convert transit detections to lane wise detections.
        self._transit_to_lane_map: np.ndarray | None = None

    def entry_node_ids(self) -> list[str]:
        """List of entering lane/node IDs."""
        return self._entry_node_ids

    def exit_node_ids(self, entry_node_id: str) -> list[str]:
        """List of exiting lane/node IDs for given entry node."""
        return self._exit_node_ids[entry_node_id]

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

        # Links starting from the same node share their conflicts. This ensures that
        # lane doesn't block itself by exclusively allowing a single movement which
        # could cause vehicles to back up behind.
        start_node_groups: dict[_Node, list[int]] = {}
        for idx, element in enumerate(all_elements):
            if isinstance(element, _Link):
                start_node_groups.setdefault(element.start, []).append(idx)

        for indices in start_node_groups.values():
            # If any link in the group conflicts with element J, all do
            row_max = np.max(conflict_matrix[indices, :], axis=0)
            conflict_matrix[indices, :] = row_max

            # If element I conflicts with any link in the group, all do
            col_max = np.max(conflict_matrix[:, indices], axis=1, keepdims=True)
            conflict_matrix[:, indices] = col_max

        return conflict_matrix

    def get_possible_phases(self, min_major_movements: int = 1) -> np.ndarray:
        """Generate all possible maximal phases.

        Filters out phases that do not serve at least `min_major_movements`
        major movements (through/left turns), while guaranteeing every link and
        crossing is covered by at least one phase.
        """
        all_elements = self._links + self._crossings
        num_elements = len(all_elements)

        if num_elements == 0:
            return np.empty((0, 0), dtype=int)

        # 1. Identify major element indices (Through & Left turns)
        major_indices = [
            i
            for i, element in enumerate(all_elements)
            if isinstance(element, _Link) and not element.is_minor()
        ]

        # 2. Build complement graph adjacency masks for Bron-Kerbosch
        conflict_matrix = self.generate_conflict_matrix() > 0
        np.fill_diagonal(conflict_matrix, False)

        adj = [0] * num_elements
        for i in range(num_elements):
            mask = 0
            for j in range(num_elements):
                if i != j and not conflict_matrix[i, j]:
                    mask |= 1 << j
            adj[i] = mask

        maximal_phases_masks = []

        def bk(r: int, p: int, x: int):
            if p == 0 and x == 0:
                maximal_phases_masks.append(r)
                return

            pivot_k = p | x
            pivot = (pivot_k & -pivot_k).bit_length() - 1
            temp_p = p & ~adj[pivot]

            while temp_p > 0:
                lsb = temp_p & -temp_p
                v = lsb.bit_length() - 1

                bk(r | lsb, p & adj[v], x & adj[v])

                p &= ~lsb
                x |= lsb
                temp_p &= ~lsb

        all_nodes_mask = (1 << num_elements) - 1
        bk(0, all_nodes_mask, 0)

        # 3. Evaluate maximal phases against major movement threshold
        candidate_phases = []
        for mask in set(maximal_phases_masks):
            phase = [(mask >> i) & 1 for i in range(num_elements)]
            num_major_greens = sum(phase[i] for i in major_indices)
            candidate_phases.append((mask, phase, num_major_greens))

        # Filter phases meeting the major movement threshold
        valid_phases = [
            p for _, p, count in candidate_phases if count >= min_major_movements
        ]

        # 4. Coverage Guarantee (Prevents starvation for standalone elements)
        covered_indices = {
            idx for phase in valid_phases for idx, active in enumerate(phase) if active
        }
        uncovered_indices = set(range(num_elements)) - covered_indices

        if uncovered_indices:
            for idx in uncovered_indices:
                fallback_options = [
                    (mask, p, count)
                    for mask, p, count in candidate_phases
                    if p[idx] == 1
                ]
                if fallback_options:
                    best_fallback = max(fallback_options, key=lambda x: x[2])
                    if best_fallback[1] not in valid_phases:
                        valid_phases.append(best_fallback[1])

        if not valid_phases:
            return np.empty((0, num_elements), dtype=int)

        return np.unique(np.array(valid_phases, dtype=int), axis=0)

    def to_lane_wise(self, phases: np.ndarray) -> np.ndarray:
        """Map movement wise phases to lane wise phases.

        Args:
            phases: Link wise phases matrix.

        Returns:
            Lane wise phases matrix. 1 indicates green, 0 indicates red.

        """
        if phases.size == 0:
            return np.empty((0, self._num_entry_lanes), dtype=int)

        # Build mapping matrix. This is cached for future calls.
        link_to_lane_map = self._build_link_to_lane_map()

        # Map phases to lanes by matrix multiplication.
        return (phases @ link_to_lane_map > 0).astype(int)

    def _build_link_to_lane_map(self) -> np.ndarray:
        if self._link_to_lane_map is not None:
            return self._link_to_lane_map

        # Mapping matrix from links to entry lanes.
        # TODO: Currently crossings are completely ignored. The system should be able
        # to also handle pedestrian crossings in the future.
        num_elements = len(self._links) + len(self._crossings)
        link_to_lane_map = np.zeros((num_elements, self._num_entry_lanes), dtype=int)

        for i, link in enumerate(self._links):
            lane_idx = link.start.num
            link_to_lane_map[i, lane_idx] = 1

        self._link_to_lane_map = link_to_lane_map

        return link_to_lane_map

    def map_transit_detections_to_lanes(
        self,
        transit_detections: np.ndarray,
    ) -> np.ndarray:
        """Map raw transit detector counts into a lane-wise array.

        Args:
            transit_detections: Transit detections as an array. The detections should be
                in the same order as 'transit_links'.

        Returns:
            Vector containing lane wise transit vehicle counts.

        """
        mapping_matrix = self._get_transit_to_lane_map()

        return transit_detections @ mapping_matrix

    def _get_transit_to_lane_map(self) -> np.ndarray:
        """Build binary mapping matrix from transit detectors to entry lanes.

        Returns:
            Matrix of shape (num_transit_links, num_entry_lanes) where
                matrix[i, j] = 1.0 indicates transit detector i monitors entry lane j.

        """
        if self._transit_to_lane_map is not None:
            return self._transit_to_lane_map

        num_transit = len(self._transit_links)
        num_lanes = self._num_entry_lanes
        matrix = np.zeros((num_transit, num_lanes), dtype=np.float32)

        for transit_idx, link_id_str in enumerate(self._transit_links):
            # Node ID numbers must be 0-indexed.
            lane_idx = int(link_id_str)
            matrix[transit_idx, lane_idx] = 1.0

        self._transit_to_lane_map = matrix
        return matrix


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
    def __init__(self, start: _Node, end: _Node, max_node_num: int):
        self.start = start
        self.end = end
        self._total_nodes = max_node_num + 1

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

        # Link doesn't conflict with links starting from the same node.
        if self.start == other.start:
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

    def is_minor(self) -> bool:
        """Check if link serves a minor movement (right turn)."""
        offset = (self.end.num - self.start.num) % self._total_nodes
        return offset == self._total_nodes - 1


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
