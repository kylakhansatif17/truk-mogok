import argparse
import sys
from pathlib import Path
from typing import List, Optional

from algorithms.registry import AlgorithmRegistry, resolve_algorithm_key
from cases.scenario_loader import ScenarioLoader
from config.settings import DEFAULT_ALGORITHM, OUTPUT_DIR
from core.simulation_observers import (
    ConsoleReportObserver,
    TraceExportObserver,
    VisualizerSnapshotObserver,
)
from core.simulation_runner import SimulationResult, SimulationRunner
from scripts.cli_utils import collect_scenario_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.run_simulation",
        description="Data-driven simulator: jalankan satu, beberapa, atau seluruh skenario YAML.",
    )
    parser.add_argument(
        "scenarios",
        nargs="*",
        help="Path file YAML dan/atau folder skenario. Kosongkan untuk memakai default/batch.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Jalankan seluruh skenario di folder cases/scenarios.",
    )
    parser.add_argument(
        "-a",
        "--algorithm",
        default=None,
        help="Registry key/alias algoritma (mis. pathfinding, ford_fulkerson, dinic, maxflow).",
    )
    parser.add_argument(
        "--save-plots",
        action="store_true",
        help="Simpan snapshot visualisasi graf sebagai PNG ke folder output/.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Jalankan tanpa membuka jendela popup Matplotlib (cocok dengan --save-plots).",
    )
    return parser


def run_single(
    yaml_path: Path,
    algorithm_override: Optional[str] = None,
    save_plots: bool = False,
    no_show: bool = False,
) -> SimulationResult:
    loader = ScenarioLoader(yaml_path)
    metadata = loader.get_metadata()
    plan = loader.get_execution_plan()
    graph_model = loader.build_graph_model()

    algorithm_key = resolve_algorithm_key(
        algorithm_override, plan, metadata, DEFAULT_ALGORITHM
    )
    solver = AlgorithmRegistry.create(algorithm_key, graph_model)

    runner = SimulationRunner(solver=solver, plan=plan, metadata=metadata)
    runner.attach(ConsoleReportObserver())
    runner.attach(
        VisualizerSnapshotObserver(
            graph_model.nx_graph,
            save_dir=OUTPUT_DIR if save_plots else None,
            show=not no_show,
        )
    )
    runner.attach(TraceExportObserver(solver))
    return runner.execute()


def main(argv: Optional[List[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    scenario_paths = collect_scenario_paths(args.scenarios, include_all=args.all)

    for yaml_path in scenario_paths:
        run_single(
            yaml_path,
            algorithm_override=args.algorithm,
            save_plots=args.save_plots,
            no_show=args.no_show,
        )


if __name__ == "__main__":
    main(sys.argv[1:])
