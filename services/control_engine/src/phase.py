from .signal_group import SignalGroup
from .timer import Timer


class SimplePhase:
    """Group of signal groups that together form a phase."""

    def __init__(self, name: int, groups: list[SignalGroup], _: Timer) -> None:
        self.groups = groups
        self.name = name

    def __str__(self) -> str:
        """Phase as a human readable string."""
        return f"PH: {self.name}"

    # Conditional functions for operating the main controller
    # These will dictate state transfers
    #

    def phase_has_started(self) -> bool:
        """Check if any group is starting green.

        Updates phase starting time for all groups.
        """
        phase_started = any(grp.is_starting() for grp in self.groups)

        if phase_started:
            for grp in self.groups:
                grp.phase_started_at = grp.system_timer.seconds

        return phase_started

    def green_has_started(self) -> bool:
        """Check if any group is in minimum green."""
        return any(grp.is_in_min_green() for grp in self.groups)

    def one_min_green_has_ended(self) -> bool:
        """Check if at least one group is not in minimum green."""
        return any(grp.is_not_in_min_green() for grp in self.groups)

    def all_min_greens_have_ended(self):
        """Check if all groups have ended their minimum greens."""
        return all(grp.is_not_in_min_green() for grp in self.groups)

    def phase_min_time_reached(self) -> bool:
        """Check if any group in the phase has reached minimum time."""
        for grp in self.groups:
            phase_min = grp.phase_min_time_reached()
            if phase_min > 0:
                print(
                    f"Phase min time reached: {grp.group_name} , {round(phase_min, 1)}",
                )
                return True

        return False

    def phase_has_a_request(self) -> bool:
        """Check if any group is requesting green."""
        return any(grp.has_green_request() for grp in self.groups)

    def phase_has_a_requested_group_wihthout_conflicts(self) -> bool:
        """Check if any requesting group has all conflicting groups red."""
        return any(
            grp.has_green_request() and grp.all_conflicts_red() for grp in self.groups
        )

    def all_active_greens_have_ended(self):
        """Check if all groups have ended their active greens."""
        return all(grp.active_gree_passed() for grp in self.groups)

    def set_permit_greens(self):
        """Set green permit to all groups."""
        for grp in self.groups:
            grp.permit_green = True

    def set_signalgroup_green_permissions(self, do_permit: bool = True) -> None:
        """Assign individual green permissions to qualifying signal groups.

        Evaluates active green conflicts and handles pedestrian/vehicle group
        interactions.
        """
        for group in self.groups:
            if group.has_green_request() and group.conflicting_active_green_passed():
                group.permit_green = do_permit
                # Remove any previous green permission in conflict
                group.remove_conflicting_green_permissions()

        # Remove green permission from pedestrian groups
        # if a yielding vehicle group has started
        for group in self.groups:
            if (
                group.permit_green
                and group.request_green
                and group.group_name == "group15"
            ):
                for disabling_group in group.disabling_groups:
                    if (
                        disabling_group.is_starting()
                        or disabling_group.group_green_or_amber()
                    ):
                        group.request_green = False
                        group.permit_green = False
