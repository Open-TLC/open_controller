from typing import Any

from services.control_engine.src.detectors.configuration import DetectorConfiguration

AMBER_LENGTH: float = 1


class SyvariControllerConfiguration:
    """Configuration object for SYVARI signal controller."""

    def __init__(self, name: str, controller_configuration: dict[str, Any]) -> None:
        self.name = name
        self.sumo_name = controller_configuration["sumo_name"]

        # This is a list of group names used to translate
        # signal group states to SUMO signal groups.
        self.state_format = controller_configuration["group_outputs"]

        # This is a list of group names used to assign an index to all groups.
        groups_order: list[str] = controller_configuration["group_list"]
        # This is a phase count * group count matrix of 0 and 1
        # depending on if group is green or not in a phase.
        phases_matrix: list[list[int]] = controller_configuration["phases"]
        # Group count * group count matrix of intergreen times between groups.
        intergreen_matrix: list[list[float]] = controller_configuration["intergreens"]

        # Intergreen times by group name.
        intergreens_by_name: dict[str, list[float]] = _get_intergreens_by_group(
            groups_order,
            intergreen_matrix,
        )

        # Safety check for conflicting phases
        if _contains_conflicting_phase(phases_matrix, intergreen_matrix):
            raise ValueError("Configured phases contain conflicts")

        # Convert the phase matrix to a matrix of active group names.
        # Group names are easier to handle later.
        self.phases = _get_active_groups_by_phase(groups_order, phases_matrix)

        self.group_confs: list[SyvariGroupConfiguration] = []

        det_confs_by_group = _get_detector_configurations_by_group(
            controller_configuration,
        )

        signal_groups = controller_configuration["signal_groups"]
        for group_name in signal_groups:
            sync_start: float = signal_groups[group_name]["sync_start"]
            sync_end: float = signal_groups[group_name]["sync_end"]
            min_green: float = signal_groups[group_name]["min_green"]
            min_guaranteed: float = signal_groups[group_name]["min_guaranteed"]
            priority_max: float = signal_groups[group_name].get("priority_max")

            # Get the green end yellow time based on the phases and intergreens.
            green_end_yellow_time: float = _get_green_end_yellow_time(
                group_name,
                intergreens_by_name,
            )

            group_conf = SyvariGroupConfiguration(
                group_name,
                sync_start,
                sync_end,
                min_green,
                min_guaranteed,
                green_end_yellow_time,
                AMBER_LENGTH,  # TODO: Read amber length from configuration file
                det_confs_by_group[group_name],
                priority_max=priority_max,
            )

            self.group_confs.append(group_conf)


def _contains_conflicting_phase(
    phases: list[list[int]],
    intergreens: list[list[float]],
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

                # If conflicting group is active in the same
                # phase, we have a conflict in the phase
                if phase[j] != 0:
                    return True

    return False


def _get_intergreens_by_group(
    groups: list[str],
    intergreens: list[list[float]],
) -> dict[str, list[float]]:
    res: dict[str, list[float]] = {}
    for i in range(len(groups)):
        res[groups[i]] = intergreens[i]

    return res


def _get_green_end_yellow_time(
    group_name: str,
    intergreens_by_group: dict[str, list[float]],
) -> float:
    return max(intergreens_by_group[group_name])


def _get_conflicting_groups(
    groups: list[str],
    group_intergreens: list[float],
) -> list[str]:
    conflict_groups: list[str] = []
    for i in range(len(groups)):
        if group_intergreens[i] != 0:
            conflict_groups.append(groups[i])

    return conflict_groups


def _get_active_groups_by_phase(
    groups_order: list[str],
    phase_matrix: list[list[int]],
) -> list[list[str]]:
    """Map a binary phase matrix to a list of active signal group names per phase.

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
    controller_conf: dict[str, Any],
) -> dict[str, list[DetectorConfiguration]]:
    """Group detector configurations by their associated signal group names.

    Args:
        controller_conf: Configuration for the entire controller.

    Returns:
        A dictionary mapping signal group names to a list of detector
        configurations belonging to that group.

    """
    detector_confs_by_id: dict[str, DetectorConfiguration] = {}
    for det_conf_dict in controller_conf["detectors"]:
        det_conf = DetectorConfiguration(det_conf_dict)

        detector_confs_by_id[det_conf.id] = det_conf

    detector_confs_by_group: dict[str, list[DetectorConfiguration]] = {}

    for group_name, group_conf in controller_conf["signal_groups"].items():
        detector_confs_by_group[group_name] = _get_detector_confs(
            group_conf["detectors"],
            detector_confs_by_id,
        )

    return detector_confs_by_group


def _get_detector_confs(
    target_detector_ids: list[str],
    detector_confs: dict[str, DetectorConfiguration],
) -> list[DetectorConfiguration]:
    result: list[DetectorConfiguration] = []
    for det_id in target_detector_ids:
        det_conf = detector_confs.get(det_id)
        if not det_conf:
            raise ValueError(f"No detector {det_id} configured")

        result.append(det_conf)

    return result


class SyvariGroupConfiguration:
    """Configuration object for SYVARI signal group."""

    def __init__(
        self,
        name: str,
        sync_start: float,
        sync_end: float,
        min_green: float,
        min_guaranteed: float,
        green_end_yellow: float,
        red_end_yellow: float,
        detector_confs: list[DetectorConfiguration],
        priority_max: float | None = None,
    ) -> None:
        self.name = name
        self.sync_start = sync_start
        self.sync_end = sync_end
        self.min_green = min_green
        self.min_guaranteed = min_guaranteed
        self.yellow = green_end_yellow
        self.amber = red_end_yellow
        self.detector_confs = detector_confs
        self.priority_max = priority_max
