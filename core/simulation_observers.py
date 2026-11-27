from pathlib import Path
from typing import Any, Dict, Optional

from core.base_algorithm import BaseGraphAlgorithm
from core.simulation_runner import RerouteResult, SimulationObserver, SimulationResult
from core.visualizer import SimpleGraphVisualizer


class ConsoleReportObserver(SimulationObserver):

    def on_initial_route(self, result: SimulationResult) -> None:
        print(f"=== RUNNING SIMULATION: {result.metadata['title']} ===")
        print(f"Algorithm: {result.algorithm_name}")
        if result.initial_flow is not None:
            print(
                f"-> {result.metric_label} Awal : {result.initial_cost:g} "
                f"| Min-Cut (Bottleneck): {result.initial_min_cut}"
            )
        else:
            print(f"-> Rute Awal  : {result.initial_path} (Cost: {result.initial_cost})")

    def on_reroute(self, result: SimulationResult, reroute: RerouteResult) -> None:
        print(f"\n[EVENT INJECTED] {reroute.description}")
        if reroute.flow is not None:
            print(
                f"-> {result.metric_label} Baru : {reroute.cost:g} "
                f"| Min-Cut (Bottleneck): {reroute.min_cut}"
            )
        else:
            print(f"-> Rute Baru  : {reroute.path} (Cost: {reroute.cost})")

    def on_event_skipped(self, result: SimulationResult, event: Dict[str, Any]) -> None:
        print(
            f"\n[EVENT SKIPPED] {event.get('type')} "
            f"tidak didukung oleh {result.algorithm_name} (butuh algoritma kategori lain)."
        )


class VisualizerSnapshotObserver(SimulationObserver):

    def __init__(self, graph: Any, save_dir: Optional[Path] = None, show: bool = True):
        self.visualizer = SimpleGraphVisualizer(graph)
        self.save_dir = Path(save_dir) if save_dir is not None else None
        self.show = show
        self._event_counter = 0

    def _build_save_path(self, result: SimulationResult, suffix: str) -> Optional[Path]:
        if self.save_dir is None:
            return None
        self.save_dir.mkdir(parents=True, exist_ok=True)
        case_id = result.metadata.get("case_id", "scenario")
        algo = result.algorithm_name.lower()
        return self.save_dir / f"plot_{case_id}_{algo}_{suffix}.png"

    def on_initial_route(self, result: SimulationResult) -> None:
        self._event_counter = 0
        save_path = self._build_save_path(result, "initial")
        if result.initial_flow is not None:
            self.visualizer.draw_snapshot(
                title=(
                    f"Kondisi Normal ({result.algorithm_name}) - {result.metadata['title']}\n"
                    f"Max Flow: {result.initial_cost:g} | Min-Cut: {result.initial_min_cut}"
                ),
                flow_distribution=result.initial_flow,
                min_cut_edges=result.initial_min_cut,
                save_path=save_path,
                show=self.show,
            )
        else:
            self.visualizer.draw_snapshot(
                title=(
                    f"Kondisi Normal - {result.metadata['title']}\n"
                    f"Rute Awal: {result.initial_path} (Cost: {result.initial_cost})"
                ),
                active_path=result.initial_path,
                save_path=save_path,
                show=self.show,
            )

    def on_reroute(self, result: SimulationResult, reroute: RerouteResult) -> None:
        self._event_counter += 1
        save_path = self._build_save_path(result, f"event_{self._event_counter}")
        if reroute.flow is not None:
            self.visualizer.draw_snapshot(
                title=(
                    f"Event #{self._event_counter} ({result.algorithm_name}): {reroute.description}\n"
                    f"Max Flow Baru: {reroute.cost:g} | Min-Cut: {reroute.min_cut}"
                ),
                highlighted_edge=reroute.target_edge,
                flow_distribution=reroute.flow,
                min_cut_edges=reroute.min_cut,
                save_path=save_path,
                show=self.show,
            )
        else:
            self.visualizer.draw_snapshot(
                title=(
                    f"Event: {reroute.description}\n"
                    f"Rute Baru: {reroute.path} (Cost: {reroute.cost})"
                ),
                active_path=reroute.path,
                highlighted_edge=reroute.target_edge,
                save_path=save_path,
                show=self.show,
            )


class TraceExportObserver(SimulationObserver):

    def __init__(self, solver: BaseGraphAlgorithm):
        self.solver = solver

    def on_complete(self, result: SimulationResult) -> None:
        registry_key = getattr(self.solver, "REGISTRY_KEY", None)
        if registry_key:
            filename = f"output_{result.metadata['case_id']}_{registry_key}.json"
        else:
            filename = f"output_{result.metadata['case_id']}.json"

        saved_path = self.solver.export_trace_json(
            filename,
            metadata={**result.metadata, "algorithm": result.algorithm_name},
        )
        print(f"\n[SUCCESS] Quantitative Trace Log exported to: {saved_path}")
