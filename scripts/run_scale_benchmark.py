"""Uji skala sintetis (V = 20, 50, 100, ...) untuk membandingkan Ford-Fulkerson vs Dinic.

Digunakan oleh Anggota 4 untuk menganalisis trade-off Overkill vs Optimal serta
efektivitas Incremental Residual Repair dibanding Full Re-computation.
"""

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt

from algorithms.registry import AlgorithmRegistry
from config.settings import OUTPUT_DIR
from core.graph_model import SpatialGraphModel
from core.simulation_runner import SimulationRunner

DEFAULT_SIZES = [20, 50, 100, 200]


def build_synthetic_road_network(
    num_nodes: int, seed: int = 42
) -> Tuple[SpatialGraphModel, Tuple[int, int], float]:
    """Membangun graf jaringan jalan sintetis berlapis dengan V simpul.

    Mengembalikan (model, target_edge, original_capacity) di koridor tengah
    untuk simulasi gangguan dinamis (tutup total -> buka 1 lajur 40%).
    """
    if num_nodes < 6:
        raise ValueError("num_nodes minimal 6")

    rng = random.Random(seed)
    model = SpatialGraphModel()

    # Susun simpul internal dalam grid berlapis (4 simpul per lapis)
    width = 4
    internal_nodes = list(range(1, num_nodes - 1))
    layers: List[List[int]] = [
        internal_nodes[i : i + width] for i in range(0, len(internal_nodes), width)
    ]

    model.add_spatial_node(0, label="S - Source", pos=(0.0, 1.5))
    for layer_idx, layer in enumerate(layers, start=1):
        for row_idx, node_id in enumerate(layer):
            model.add_spatial_node(
                node_id, label=f"N{node_id}", pos=(float(layer_idx * 2), float(row_idx))
            )
    model.add_spatial_node(
        num_nodes - 1, label="T - Sink", pos=(float((len(layers) + 1) * 2), 1.5)
    )

    def _add_road(u: int, v: int, cap: float, bidir: bool = True) -> None:
        dist = round(rng.uniform(0.15, 0.85), 3)
        model.add_weighted_edge(u, v, weight=dist, capacity=cap)
        if bidir:
            model.add_weighted_edge(v, u, weight=dist, capacity=cap)

    # Source ke lapis pertama & lapis terakhir ke Sink
    for n in layers[0]:
        _add_road(0, n, round(rng.uniform(800.0, 1400.0), 1), bidir=False)
    for n in layers[-1]:
        _add_road(n, num_nodes - 1, round(rng.uniform(800.0, 1400.0), 1), bidir=False)

    # Koneksi antar lapis + jalan silang dalam lapis (menyerupai grid jalan kota)
    mid_layer_idx = max(0, len(layers) // 2 - 1)
    target_edge: Optional[Tuple[int, int]] = None
    target_cap: float = 0.0

    for idx in range(len(layers) - 1):
        curr_layer = layers[idx]
        next_layer = layers[idx + 1]

        # Koneksi intra-layer (jalan penghubung antar koridor)
        for j in range(len(curr_layer) - 1):
            _add_road(curr_layer[j], curr_layer[j + 1], round(rng.uniform(500.0, 1000.0), 1))

        # Koneksi inter-layer (lurus & diagonal)
        for j, u in enumerate(curr_layer):
            v_main = next_layer[min(j, len(next_layer) - 1)]
            cap_main = round(rng.uniform(650.0, 1300.0), 1)
            _add_road(u, v_main, cap_main)
            if idx == mid_layer_idx and target_edge is None:
                target_edge = (u, v_main)
                target_cap = cap_main

            if j + 1 < len(next_layer):
                _add_road(u, next_layer[j + 1], round(rng.uniform(450.0, 950.0), 1))
            if j - 1 >= 0 and j - 1 < len(next_layer):
                _add_road(u, next_layer[j - 1], round(rng.uniform(450.0, 950.0), 1))

    assert target_edge is not None
    return model, target_edge, target_cap


def run_scale_trial(num_nodes: int, seed: int) -> Dict[str, Any]:
    """Menjalankan satu percobaan komparasi FordFulkerson vs Dinic pada ukuran V."""
    model_ff, target_edge, orig_cap = build_synthetic_road_network(num_nodes, seed=seed)
    model_dn, _, _ = build_synthetic_road_network(num_nodes, seed=seed)

    plan = {
        "start_node": 0,
        "goal_node": num_nodes - 1,
        "events": [
            {
                "step": 1,
                "type": "DYNAMIC_EDGE_CAPACITY",
                "target_edge": list(target_edge),
                "new_capacity": 0.0,
                "description": "Gangguan total pada ruas tengah",
            },
            {
                "step": 2,
                "type": "DYNAMIC_EDGE_CAPACITY",
                "target_edge": list(target_edge),
                "new_capacity": round(orig_cap * 0.4, 1),
                "description": "Pembukaan 1 lajur parsial (40%)",
            },
        ],
    }
    metadata = {"case_id": f"synthetic_v{num_nodes}_s{seed}"}

    solver_ff = AlgorithmRegistry.create("ford_fulkerson", model_ff)
    res_ff = SimulationRunner(solver=solver_ff, plan=plan, metadata=metadata).execute()

    solver_dn = AlgorithmRegistry.create("dinic", model_dn)
    res_dn = SimulationRunner(solver=solver_dn, plan=plan, metadata=metadata).execute()

    if abs(res_ff.initial_cost - res_dn.initial_cost) > 1e-6:
        raise AssertionError(
            f"Mismatch initial max flow V={num_nodes}: FF={res_ff.initial_cost} vs Dinic={res_dn.initial_cost}"
        )
    if abs(res_ff.reroutes[-1].cost - res_dn.reroutes[-1].cost) > 1e-6:
        raise AssertionError(
            f"Mismatch post-event max flow V={num_nodes}: FF={res_ff.reroutes[-1].cost} vs Dinic={res_dn.reroutes[-1].cost}"
        )

    return {
        "V": model_ff.nx_graph.number_of_nodes(),
        "E": model_ff.nx_graph.number_of_edges(),
        "ff_steps": solver_ff.step_count,
        "dn_steps": solver_dn.step_count,
        "ff_init_ms": res_ff.initial_elapsed_ms,
        "dn_init_ms": res_dn.initial_elapsed_ms,
        "ff_dyn_ms": sum(r.elapsed_ms for r in res_ff.reroutes),
        "dn_dyn_ms": sum(r.elapsed_ms for r in res_dn.reroutes),
        "init_flow": res_ff.initial_cost,
        "post_flow": res_ff.reroutes[-1].cost,
    }


def benchmark_scales(sizes: List[int], trials: int = 5) -> List[Dict[str, Any]]:
    """Menjalankan benchmark agregat (median) untuk beberapa ukuran graf."""
    summary: List[Dict[str, Any]] = []
    for v in sizes:
        runs = [run_scale_trial(v, seed=100 + t) for t in range(trials)]
        ff_init = statistics.median(r["ff_init_ms"] for r in runs)
        dn_init = statistics.median(r["dn_init_ms"] for r in runs)
        ff_dyn = statistics.median(r["ff_dyn_ms"] for r in runs)
        dn_dyn = statistics.median(r["dn_dyn_ms"] for r in runs)
        ff_total = ff_init + ff_dyn
        dn_total = dn_init + dn_dyn

        summary.append(
            {
                "V": runs[0]["V"],
                "E": runs[0]["E"],
                "trials": trials,
                "ff_steps": round(statistics.median(r["ff_steps"] for r in runs), 1),
                "dn_steps": round(statistics.median(r["dn_steps"] for r in runs), 1),
                "ff_init_ms": round(ff_init, 4),
                "dn_init_ms": round(dn_init, 4),
                "ff_dyn_ms": round(ff_dyn, 4),
                "dn_dyn_ms": round(dn_dyn, 4),
                "ff_total_ms": round(ff_total, 4),
                "dn_total_ms": round(dn_total, 4),
                "dyn_speedup": round(ff_dyn / dn_dyn, 2) if dn_dyn > 0 else 0.0,
                "total_speedup": round(ff_total / dn_total, 2) if dn_total > 0 else 0.0,
            }
        )
    return summary


def save_outputs(summary: List[Dict[str, Any]], out_dir: Path = OUTPUT_DIR) -> None:
    """Menyimpan hasil benchmark skala ke JSON dan grafik perbandingan PNG."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "scale_benchmark_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    vs = [row["V"] for row in summary]
    ff_totals = [row["ff_total_ms"] for row in summary]
    dn_totals = [row["dn_total_ms"] for row in summary]
    ff_dyns = [row["ff_dyn_ms"] for row in summary]
    dn_dyns = [row["dn_dyn_ms"] for row in summary]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))

    axes[0].plot(vs, ff_totals, marker="o", linewidth=2, color="#d62728", label="Ford-Fulkerson (Full Recompute)")
    axes[0].plot(vs, dn_totals, marker="s", linewidth=2, color="#1f77b4", label="Dinic (Incremental Repair)")
    axes[0].set_title("Total Runtime (Init + 2 Dynamic Events)")
    axes[0].set_xlabel("Jumlah Simpul (V)")
    axes[0].set_ylabel("Median Runtime (ms)")
    axes[0].grid(True, linestyle="--", alpha=0.5)
    axes[0].legend()

    axes[1].plot(vs, ff_dyns, marker="o", linewidth=2, color="#d62728", label="Ford-Fulkerson (Dynamic)")
    axes[1].plot(vs, dn_dyns, marker="s", linewidth=2, color="#1f77b4", label="Dinic (Incremental)")
    axes[1].set_title("Dynamic Re-evaluation Runtime Only")
    axes[1].set_xlabel("Jumlah Simpul (V)")
    axes[1].set_ylabel("Median Dynamic Runtime (ms)")
    axes[1].grid(True, linestyle="--", alpha=0.5)
    axes[1].legend()

    fig.suptitle("Uji Skala Sintetis: Overkill vs Optimal (Ford-Fulkerson vs Dinic)", fontsize=12, fontweight="bold")
    fig.tight_layout()
    plot_path = out_dir / "plot_scale_benchmark.png"
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"[SAVED] {json_path}")
    print(f"[SAVED] {plot_path}")


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Uji skala sintetis Ford-Fulkerson vs Dinic.")
    parser.add_argument("--sizes", nargs="+", type=int, default=DEFAULT_SIZES, help="Daftar ukuran V.")
    parser.add_argument("--trials", type=int, default=5, help="Jumlah seed percobaan per ukuran.")
    parser.add_argument("--save", action="store_true", help="Simpan JSON & PNG plot ke output/.")
    args = parser.parse_args(argv)

    summary = benchmark_scales(args.sizes, trials=args.trials)

    print("\n------------------------ SCALE BENCHMARK (MEDIAN) ------------------------")
    print(
        f" {'V':>4} {'E':>5} | {'FF Init(ms)':>11} {'DN Init(ms)':>11} | "
        f"{'FF Dyn(ms)':>10} {'DN Dyn(ms)':>10} | {'Dyn Speedup':>11} {'Total Speedup':>13}"
    )
    print(" " + "-" * 86)
    for row in summary:
        print(
            f" {row['V']:>4} {row['E']:>5} | {row['ff_init_ms']:>11.4f} {row['dn_init_ms']:>11.4f} | "
            f"{row['ff_dyn_ms']:>10.4f} {row['dn_dyn_ms']:>10.4f} | "
            f"{row['dyn_speedup']:>10.2f}x {row['total_speedup']:>12.2f}x"
        )
    print(" " + "-" * 86)

    if args.save:
        save_outputs(summary)


if __name__ == "__main__":
    main(sys.argv[1:])
