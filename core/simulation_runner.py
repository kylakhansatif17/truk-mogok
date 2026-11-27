import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.base_algorithm import BaseGraphAlgorithm


@dataclass
class RerouteResult:
    description: str
    target_edge: Tuple[int, int]
    new_weight: Optional[float] = None
    path: List[int] = field(default_factory=list)
    cost: float = 0.0
    elapsed_ms: float = 0.0
    event_type: str = "DYNAMIC_EDGE_WEIGHT"
    new_capacity: Optional[float] = None
    flow: Optional[Dict[Tuple[int, int], float]] = None
    min_cut: List[Tuple[int, int]] = field(default_factory=list)


@dataclass
class SimulationResult:
    metadata: Dict[str, Any]
    algorithm_name: str
    initial_path: List[int]
    initial_cost: float
    initial_elapsed_ms: float
    reroutes: List[RerouteResult] = field(default_factory=list)
    skipped_events: List[Dict[str, Any]] = field(default_factory=list)
    metric_label: str = "Cost"
    initial_flow: Optional[Dict[Tuple[int, int], float]] = None
    initial_min_cut: List[Tuple[int, int]] = field(default_factory=list)


class SimulationObserver:

    def on_initial_route(self, result: SimulationResult) -> None:
        pass

    def on_reroute(self, result: SimulationResult, reroute: RerouteResult) -> None:
        pass

    def on_event_skipped(self, result: SimulationResult, event: Dict[str, Any]) -> None:
        pass

    def on_complete(self, result: SimulationResult) -> None:
        pass


class SimulationRunner:

    def __init__(
        self,
        solver: BaseGraphAlgorithm,
        plan: Dict[str, Any],
        metadata: Dict[str, Any],
        observers: Optional[List[SimulationObserver]] = None,
    ):
        self.solver = solver
        self.plan = plan
        self.metadata = metadata
        self.observers: List[SimulationObserver] = list(observers or [])

    def attach(self, observer: SimulationObserver) -> None:
        self.observers.append(observer)

    @staticmethod
    def _unpack_solver_output(raw_output: Any) -> Tuple[List[int], float]:
        if isinstance(raw_output, tuple) and len(raw_output) == 2:
            return raw_output[0], float(raw_output[1])
        return [], float(raw_output)

    def _extract_flow_state(
        self,
    ) -> Tuple[Optional[Dict[Tuple[int, int], float]], List[Tuple[int, int]]]:
        flow = (
            self.solver.get_flow_distribution()
            if hasattr(self.solver, "get_flow_distribution")
            else None
        )
        min_cut = (
            self.solver.get_min_cut()
            if hasattr(self.solver, "get_min_cut")
            else []
        )
        return flow, min_cut

    def execute(self) -> SimulationResult:
        start_node = self.plan["start_node"]
        goal_node = self.plan["goal_node"]

        t_start = time.perf_counter()
        raw_initial = self.solver.run(start_node, goal_node)
        initial_elapsed_ms = (time.perf_counter() - t_start) * 1000
        path, cost = self._unpack_solver_output(raw_initial)
        initial_flow, initial_min_cut = self._extract_flow_state()

        result = SimulationResult(
            metadata=self.metadata,
            algorithm_name=self.solver.__class__.__name__,
            initial_path=path,
            initial_cost=cost,
            initial_elapsed_ms=initial_elapsed_ms,
            metric_label=getattr(self.solver, "METRIC_LABEL", "Cost"),
            initial_flow=initial_flow,
            initial_min_cut=initial_min_cut,
        )
        self._notify("on_initial_route", result)

        supported_types = getattr(self.solver, "SUPPORTED_EVENT_TYPES", None)
        for event in self.plan.get("events", []):
            if supported_types is not None and event.get("type") not in supported_types:
                result.skipped_events.append(event)
                self._notify("on_event_skipped", result, event)
                continue
            reroute = self._execute_event(event, start_node, goal_node)
            result.reroutes.append(reroute)
            self._notify("on_reroute", result, reroute)

        self._notify("on_complete", result)
        return result

    def _execute_event(
        self, event: Dict[str, Any], start_node: int, goal_node: int
    ) -> RerouteResult:
        target_edge = tuple(event["target_edge"])
        event_type = event.get("type", "DYNAMIC_EDGE_WEIGHT")
        event_data: Dict[str, Any] = {
            "type": event_type,
            "edge": target_edge,
            "start": start_node,
            "goal": goal_node,
            "source": start_node,
            "sink": goal_node,
        }
        if "new_weight" in event:
            event_data["new_weight"] = event["new_weight"]
        if "new_capacity" in event:
            event_data["new_capacity"] = event["new_capacity"]

        t_start = time.perf_counter()
        raw_output = self.solver.handle_dynamic_event(event_data)
        elapsed_ms = (time.perf_counter() - t_start) * 1000
        path, cost = self._unpack_solver_output(raw_output)
        flow, min_cut = self._extract_flow_state()

        return RerouteResult(
            description=event.get("description", ""),
            target_edge=target_edge,
            new_weight=event.get("new_weight"),
            path=path,
            cost=cost,
            elapsed_ms=elapsed_ms,
            event_type=event_type,
            new_capacity=event.get("new_capacity"),
            flow=flow,
            min_cut=min_cut,
        )

    def _notify(self, hook: str, *args) -> None:
        for observer in self.observers:
            getattr(observer, hook)(*args)
