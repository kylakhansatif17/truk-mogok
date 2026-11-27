import argparse
import sys
from pathlib import Path
from typing import List, Optional

from algorithms.registry import AlgorithmRegistry, resolve_algorithm_key
from cases.scenario_loader import ScenarioLoader
from config.settings import DEFAULT_ALGORITHM
from core.simulation_runner import SimulationRunner
from scripts.cli_utils import collect_scenario_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.run_benchmark",
        description="Benchmark runtime & step count untuk satu, beberapa, atau seluruh skenario.",
    )
    parser.add_argument(
        "scenarios",
        nargs="*",
        help="Path file YAML dan/atau folder skenario. Kosongkan untuk memakai default/batch.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Benchmark seluruh skenario di folder cases/scenarios.",
    )
    parser.add_argument(
        "-a",
        "--algorithm",
        default=None,
        help="Registry key/alias algoritma (mis. pathfinding, ford_fulkerson, dinic, maxflow).",
    )
    parser.add_argument(
        "--compare",
        nargs="+",
        default=None,
        help="Bandingkan beberapa algoritma pada skenario yang sama (mis. --compare ford_fulkerson dinic).",
    )
    return parser


def run_single(
    yaml_path: Path, algorithm_override: Optional[str] = None
):
    loader = ScenarioLoader(yaml_path)
    metadata = loader.get_metadata()
    plan = loader.get_execution_plan()
    graph_model = loader.build_graph_model()

    algorithm_key = resolve_algorithm_key(
        algorithm_override, plan, metadata, DEFAULT_ALGORITHM
    )
    solver = AlgorithmRegistry.create(algorithm_key, graph_model)

    result = SimulationRunner(solver=solver, plan=plan, metadata=metadata).execute()
    return algorithm_key, solver, result


def main(argv: Optional[List[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    scenario_paths = collect_scenario_paths(args.scenarios, include_all=args.all)
    algorithms_to_run = args.compare if args.compare else [args.algorithm]

    rows = []
    for yaml_path in scenario_paths:
        for algo_override in algorithms_to_run:
            _, solver, result = run_single(yaml_path, algorithm_override=algo_override)
            post_val = result.reroutes[-1].cost if result.reroutes else result.initial_cost
            final_min_cut = (
                result.reroutes[-1].min_cut if result.reroutes else result.initial_min_cut
            )
            rows.append(
                {
                    "case": result.metadata.get("case_id", yaml_path.stem),
                    "algorithm": result.algorithm_name,
                    "steps": solver.step_count,
                    "init_val": result.initial_cost,
                    "post_val": post_val,
                    "initial_ms": result.initial_elapsed_ms,
                    "reroute_ms": sum(r.elapsed_ms for r in result.reroutes),
                    "min_cut": str(final_min_cut) if final_min_cut else "-",
                }
            )

    print("\n------------------------------------- BENCHMARK RESULTS -------------------------------------")
    print(
        f" {'Case':<28} {'Algorithm':<15} {'Steps':>6} "
        f"{'InitVal':>8} {'PostVal':>8} {'Init(ms)':>10} {'Dyn(ms)':>10}  {'Min-Cut'}"
    )
    print(" " + "-" * 105)
    for row in rows:
        print(
            f" {row['case']:<28} {row['algorithm']:<15} {row['steps']:>6} "
            f"{row['init_val']:>8.1f} {row['post_val']:>8.1f} "
            f"{row['initial_ms']:>10.4f} {row['reroute_ms']:>10.4f}  {row['min_cut']}"
        )
    print(" " + "-" * 105)
    print(f" Total runs: {len(rows)} ({len(scenario_paths)} scenario(s))")
    print("----------------------------------------------------------------------------------------------")


if __name__ == "__main__":
    main(sys.argv[1:])
