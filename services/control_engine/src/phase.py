from .signal_group import SignalGroup


class SimplePhase:
    """Group of signal groups that together form a control phase."""

    def __init__(self, name: int, groups: list[SignalGroup]) -> None:
        self.name = name
        self.groups = groups

    def __str__(self) -> str:
        return f"PH: {self.name}"

    def phase_has_started(self) -> bool:
        """Check if any group in the phase has entered green state."""
        return any(grp.state.startswith("Green") for grp in self.groups)

    def green_has_started(self) -> bool:
        """Check if any group is in minimum green."""
        return any(grp.state == "Green_MinimumTime" for grp in self.groups)

    def one_min_green_has_ended(self) -> bool:
        """Check if at least one group has finished minimum green."""
        return any(grp.state != "Green_MinimumTime" for grp in self.groups)

    def all_min_greens_have_ended(self) -> bool:
        """Check if all groups have finished minimum green."""
        return all(grp.state != "Green_MinimumTime" for grp in self.groups)

    def phase_has_a_request(self) -> bool:
        """Check if any group in the phase is requesting green."""
        return any(grp.is_requesting for grp in self.groups)

    def all_active_greens_have_ended(self) -> bool:
        """Check if all active greens have ended (no groups extending)."""
        return all(not grp.is_extending for grp in self.groups)

    def set_signalgroup_green_permissions(self, do_permit: bool = True) -> None:
        """Assign green permissions to requesting groups clear of blocking conflicts."""
        for grp in self.groups:
            grp.green_permission = do_permit
