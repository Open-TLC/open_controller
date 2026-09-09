import sys
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, TypedDict

from transitions.extensions import HierarchicalGraphMachine, HierarchicalMachine
from transitions.extensions.diagrams_graphviz import NestedGraph

from services.control_engine.src.configuration import ClockworkConf, read_command_line
from services.control_engine.src.extenders.extender import Extender
from services.control_engine.src.requesters.requester import Requester

from .timer import Timer

BLOCKING_STATES: set[str] = {"g", "0", "1", "4", "5", "<"}

MACHINE_STATE_TO_OC_MAP: dict[str, str] = {
    "Red_MinimumTime": "a",
    "Red_WaitRequestAndPermission": "b",
    "Red_EndingConflicts": "f",
    "Red_WaitIntergreen": "g",
    "AmberRed_MinimumTime": "0",
    "Green_MinimumTime": "1",
    "Green_Extending": "5",
    "Green_RemainGreen": "4",
    "Amber_MinimumTime": "<",
}


class SignalGroupConfig(TypedDict):
    """Configuration options for a signal group."""

    min_amber_red: float
    min_green: float
    max_green: float
    remain_green: bool
    min_amber: float
    min_red: float
    constant_request: bool


class SignalGroup(HierarchicalMachine):
    """Signal group used in group based control."""

    state: str
    next_state: Callable[[], bool]

    def __init__(
        self,
        timer: Timer,
        group_id: str,
        group_conf: SignalGroupConfig,
        intergreens: dict[str, float],
    ) -> None:
        """Create new signal group.

        Args:
            timer: Timer object used by the controller.
            group_id: Unique ID of the signal group.
            group_conf: Configuration parameters for timing and behavior rules.
            intergreens: Dictionary of intergreen times by ending group ID.

        """
        self._id = group_id
        self._timer = timer
        self._intergreens = intergreens

        self.conflict_groups: list[SignalGroup] = []

        self._extenders: list[Extender] = []
        self._requesters: list[Requester] = []

        self._constant_request: bool = group_conf["constant_request"]

        self.green_permission: bool = False

        self.end_green_requested: bool = False

        self.amber_started_at: float = 0.0
        self.green_started_at: float = 0.0

        self._amber_red_length: float = group_conf["min_amber_red"]

        # Signal group has four main states: Amber red, green, amber, and red.
        # They are all sub state machines and will trigger the exit transitions
        # themselves. This triggers the main state to transition to the next main state.
        self._amber_red_state: HierarchicalMachine = FixedTime(
            self._timer,
            self,
            group_conf["min_amber_red"],
        )

        self._green_state: HierarchicalMachine = ExtendedGreen(
            self._timer,
            self,
            group_conf["min_green"],
            group_conf["max_green"],
            group_conf["remain_green"],
        )

        self._amber_state: HierarchicalMachine = FixedTime(
            self._timer,
            self,
            group_conf["min_amber"],
        )

        self._red_state: HierarchicalMachine = GroupBasedRed(
            self._timer,
            self,
            group_conf["min_red"],
        )

        states = [
            {
                "name": "Red",
                "children": self._red_state,
            },
            {"name": "AmberRed", "children": self._amber_red_state},
            {
                "name": "Green",
                "children": self._green_state,
                "on_enter": self._green_start_cb,
            },
            {
                "name": "Amber",
                "on_enter": self._amber_start_cb,
                "children": self._amber_state,
            },
        ]

        transitions = [
            {
                "trigger": "next_state",
                "source": "Red_Exit",
                "dest": "AmberRed_MinimumTime",
            },
            {
                "trigger": "next_state",
                "source": "AmberRed_Exit",
                "dest": "Green_MinimumTime",
            },
            {
                "trigger": "next_state",
                "source": "Green_Exit",
                "dest": "Amber_MinimumTime",
            },
            {
                "trigger": "next_state",
                "source": "Amber_Exit",
                "dest": "Red_MinimumTime",
            },
        ]

        super().__init__(
            name=self._id,
            states=states,
            transitions=transitions,
            initial="Red",
            auto_transitions=False,
            queued=True,
        )

    def add_conflict_groups(self, groups: list["SignalGroup"]) -> None:
        """Add conflicting groups for the group."""
        self.conflict_groups.extend(groups)

    def add_extenders(self, extenders: list[Extender]) -> None:
        """Add extenders for the group."""
        self._extenders.extend(extenders)

    def add_requesters(self, requesters: list[Requester]) -> None:
        """Add requesters for the group."""
        self._requesters.extend(requesters)

    @property
    def id(self) -> str:
        """ID of the signal group."""
        return self._id

    @property
    def signal_state(self) -> str:
        """Groups state in OC format."""
        return MACHINE_STATE_TO_OC_MAP[self.state]

    @property
    def is_blocking(self) -> bool:
        """Group is in state, that blocks conflict groups."""
        return self.signal_state in BLOCKING_STATES

    def tick(self) -> None:
        """Update signal group."""
        for req in self._requesters:
            req.tick()

        for ext in self._extenders:
            ext.tick()

        # Try to transition to next state.
        self.next_state()

    @property
    def is_extending(self) -> bool:
        """Group is extending current green."""
        return any(ext.is_extending for ext in self._extenders)

    @property
    def is_requesting(self) -> bool:
        """Group is requesting green."""
        return (
            any(req.is_requesting for req in self._requesters) or self._constant_request
        )

    def conflict_group_blocking(self) -> bool:
        """Check if any conflicting group is blocking."""
        for grp in self.conflict_groups:
            if grp.is_blocking:
                pass
        return any(grp.is_blocking for grp in self.conflict_groups)

    def end_conflict_greens(self) -> None:
        """Request all conflicting groups to end their greens."""
        for group in self.conflict_groups:
            group.end_green_requested = True

    def intergreens_passed(self) -> bool:
        """Check if all conflict group intergreen times have passed."""
        return all(
            self._timer.seconds - grp.amber_started_at
            > self._intergreens[grp.id] - self._amber_red_length
            for grp in self.conflict_groups
        )

    def give_green_permission(self) -> None:
        """Give green permission to group and take conflict green permissions away."""
        for grp in self.conflict_groups:
            grp.green_permission = False

        self.green_permission = True

    def _amber_start_cb(self) -> None:
        self.amber_started_at = self._timer.seconds

    def _green_start_cb(self) -> None:
        self.green_started_at = self._timer.seconds


class FixedTime(HierarchicalMachine):
    """Fixed time state."""

    def __init__(self, timer: Timer, group: SignalGroup, min_length: float) -> None:
        self._group = group
        self._timer = timer
        self._min_length = min_length
        self._min_started_at: float = 0.0

        states = [
            {"name": "MinimumTime", "on_enter": self._start_minimum_time},
            {"name": "Exit", "on_enter": self._end_minimum_time},
        ]

        transitions = [
            {
                "trigger": "next_state",
                "source": "MinimumTime",
                "dest": "Exit",
                "conditions": [self._min_time_passed],
            },
        ]
        super().__init__(
            states=states,
            transitions=transitions,
            initial="MinimumTime",
            auto_transitions=False,
        )

    def _min_time_passed(self) -> bool:
        return self._min_started_at + self._min_length < self._timer.seconds

    def _start_minimum_time(self) -> None:
        self._min_started_at = self._timer.seconds
        self._group.next_state()

    def _end_minimum_time(self) -> None:
        self._group.next_state()


class ExtendedGreen(FixedTime):
    """Green phase that can be extended by groups extenders."""

    def __init__(
        self,
        timer: Timer,
        group: SignalGroup,
        min_length: float,
        max_length: float,
        remain_green: bool,
    ) -> None:
        super().__init__(timer, group, min_length)

        self._max_length = max_length

        # Remain passive green after extension if conflicting groups
        # don't request to end green.
        self._remain_green = remain_green

        # Add new states for extension and passive green.
        self.add_state("Extending")
        self.add_state("RemainGreen")

        # Don't transition away without extending.
        self.remove_transition(trigger="next_state", dest="Exit")

        # Instead transition from minimum to extending.
        self.add_transition(
            trigger="next_state",
            source="MinimumTime",
            dest="Extending",
            conditions=[self._min_time_passed],
        )

        # End green if group is no longer extending and is set to end after extension.
        self.add_transition(
            trigger="next_state",
            source="Extending",
            dest="Exit",
            conditions=[
                lambda: not self._group.is_extending or self._max_time_passed(),
                lambda: not self._remain_green,
            ],
            before=self._end_green_cb,
        )

        # Transition to passive green if group is no longer extending and is set to
        # remain green after extension.
        self.add_transition(
            trigger="next_state",
            source="Extending",
            dest="RemainGreen",
            conditions=[
                lambda: not self._group.is_extending or self._max_time_passed(),
                lambda: self._remain_green,
            ],
        )

        # End green if another group requests group to end green.
        self.add_transition(
            trigger="next_state",
            source="RemainGreen",
            dest="Exit",
            conditions=[
                self._end_green_requested,
            ],
            before=self._end_green_cb,
        )

    def _max_time_passed(self) -> bool:
        """Group has extended past its maximum allowed time."""
        return self._min_started_at + self._max_length < self._timer.seconds

    def _end_green_requested(self) -> bool:
        return self._group.end_green_requested

    def _end_green_cb(self) -> None:
        self._group.end_green_requested = False


class GroupBasedRed(FixedTime):
    """Signal group control based red state."""

    def __init__(self, timer: Timer, group: SignalGroup, min_length: float) -> None:
        super().__init__(timer, group, min_length)

        # Don't terminate red after minimum time has elapsed.
        self.remove_transition(trigger="next_state", dest="Exit")

        # At this state the group waits for a green request and permission to go green.
        self.add_state(
            "WaitRequestAndPermission",
            on_enter=self._start_waiting_req_and_perm,
        )

        # At this state the group will try to end conflicting greens.
        self.add_state("EndingConflicts", on_enter=self._start_ending_conflicts)

        # After conflicting groups have ended their greens, the group still needs to
        # wait for intergreen times to pass. At this point the eventual transition
        # to green can no longer be blocked.
        self.add_state("WaitIntergreen", on_enter=self._start_waiting_intergreen)

        # After minimum red, start waiting for request and permission.
        self.add_transition(
            trigger="next_state",
            source="MinimumTime",
            dest="WaitRequestAndPermission",
            conditions=[self._min_time_passed],
        )

        # After receiving a green request and a permission to go green, start ending
        # conflicting greens.
        self.add_transition(
            trigger="next_state",
            source="WaitRequestAndPermission",
            dest="EndingConflicts",
            conditions=[
                lambda: self._group.is_requesting,
                lambda: self._group.green_permission,
            ],
        )

        # After conflicting greens have ended, start waiting for intergreen times to
        # pass.
        self.add_transition(
            trigger="next_state",
            source="EndingConflicts",
            dest="WaitIntergreen",
            conditions=[lambda: not self._group.conflict_group_blocking()],
        )

        # After intergreens have passed, end red state.
        self.add_transition(
            trigger="next_state",
            source="WaitIntergreen",
            dest="Exit",
            conditions=[self._intergreens_passed],
        )

    def _start_waiting_req_and_perm(self) -> None:
        self._group.next_state()

    def _start_ending_conflicts(self) -> None:
        self._group.end_conflict_greens()
        self._group.next_state()

    def _start_waiting_intergreen(self) -> None:
        self._group.next_state()

    def _intergreens_passed(self) -> bool:
        return self._group.intergreens_passed()


def _style_diagram(machine, title):
    """Applies the shared diagram styling to a (Nested)GraphMachine instance.

    Every transition in these state machines uses the same trigger
    ('next_state'), so it adds no information on the diagram - show only the
    guard conditions instead, one OR-ed alternative per line.
    """
    machine.title = title
    machine.show_conditions = True
    machine.show_auto_transitions = True
    machine.show_state_attributes = True
    machine.machine_attributes = dict(machine.machine_attributes, rankdir="TB")

    class ConditionOnlyGraph(NestedGraph):
        def _transition_label(self, tran):
            if self.machine.show_conditions and any(
                p in tran for p in ("conditions", "unless")
            ):
                conditions = " & ".join(
                    tran.get("conditions", [])
                    + ["!" + u for u in tran.get("unless", [])],
                )
                return conditions + r"\l"
            return ""

        def _add_edges(self, transitions, container):
            edges_attr = defaultdict(lambda: defaultdict(dict))
            for transition in transitions:
                src = transition["source"]
                dst = transition.get("dest", src)
                if edges_attr[src][dst]:
                    attr = edges_attr[src][dst]
                    attr[attr["label_pos"]] += self._transition_label(transition)
                else:
                    edges_attr[src][dst] = self._create_edge_attr(src, dst, transition)
            for custom_src, dests in self.custom_styles["edge"].items():
                for custom_dst, style in dests.items():
                    if style and (
                        custom_src not in edges_attr
                        or custom_dst not in edges_attr[custom_src]
                    ):
                        edges_attr[custom_src][custom_dst] = self._create_edge_attr(
                            custom_src,
                            custom_dst,
                            {"trigger": "", "dest": ""},
                        )
            for src, dests in edges_attr.items():
                for dst, attr in dests.items():
                    del attr["label_pos"]
                    style = self.custom_styles["edge"][src][dst]
                    attr.update(
                        **self.machine.style_attributes.get("edge", {}).get(style, {}),
                    )
                    container.edge(attr.pop("source"), attr.pop("dest"), **attr)

    machine.graph_cls = ConditionOnlyGraph


@contextmanager
def _graph_capable():
    """Temporarily gives SignalGroup/FixedTime (and its subclasses) graph-drawing
    support by swapping in transitions' HierarchicalGraphMachine as their base
    class. Normal operation never pays for this: SignalGroup/FixedTime are
    plain HierarchicalMachine-based, with no (py)graphviz dependency and no
    per-transition graph bookkeeping - only diagram generation, inside this
    context, needs the graph-capable library.
    """
    swapped = {SignalGroup: SignalGroup.__bases__, FixedTime: FixedTime.__bases__}
    try:
        for cls in swapped:
            cls.__bases__ = (HierarchicalGraphMachine,)
        yield
    finally:
        for cls, bases in swapped.items():
            cls.__bases__ = bases


def _build_signal_group() -> SignalGroup:
    args = read_command_line()
    filename = args.conf_file
    cw_conf = ClockworkConf(filename, print_status=False)
    timer = Timer(cw_conf.timer)
    all_group_options: dict[str, Any] = cw_conf.controllers[0].options["signal_groups"]
    group_id, group_options = all_group_options.popitem()

    return SignalGroup(timer, group_id, group_options, {})


def draw_graphs():
    with _graph_capable():
        sg = _build_signal_group()
        _style_diagram(sg, "The signal group main loop")
        print("Getting the diagram")
        sg.get_graph(show_roi=False, force_new=True).draw("tmp/ring.png", prog="dot")


def draw_submachine_graphs():
    """Draws a separate diagram for each of the signal group's sub-state-machines
    (Red, AmberRed, Green, Amber).
    """
    with _graph_capable():
        sg = _build_signal_group()
        submachines = {
            "red": sg.group_based_red,
            "amber_red": sg.fixed_amber_red,
            "green": sg.va_green,
            "amber": sg.fixed_amber,
        }
        for name, machine in submachines.items():
            _style_diagram(machine, f"Signal group - {name} substate machine")
            print("Getting the diagram for", name)
            machine.get_graph(show_roi=False, force_new=True).draw(
                f"tmp/ring_{name}.png",
                prog="dot",
            )


if __name__ == "__main__":
    # --submachines draws Red/AmberRed/Green/Amber separately instead of the
    # full ring. Consumed here so confread's argparse doesn't choke on it.
    if "--submachines" in sys.argv:
        sys.argv.remove("--submachines")
        draw_submachine_graphs()
    else:
        draw_graphs()
