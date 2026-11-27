import random
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Headless rendering for automated tests

import networkx as nx
import pytest

from algorithms.registry import AlgorithmRegistry
from cases.scenario_loader import ScenarioLoader
from config.settings import CASES_DIR
from core.graph_model import SpatialGraphModel
from core.simulation_observers import (
    ConsoleReportObserver,
    TraceExportObserver,
    VisualizerSnapshotObserver,
)
from core.simulation_runner import SimulationRunner

CASE_07_PATH = CASES_DIR / "case_07_truk_mogok.yaml"


def _assert_valid_flow(graph: nx.DiGraph, source: int, sink: int, flow_map: dict, reported_flow: float):
    """Verify capacity constraints, flow conservation, and net source outflow."""
    for u, v, data in graph.edges(data=True):
        cap = float(data.get("capacity", data.get("weight", 1.0)))
        f = flow_map.get((u, v), 0.0)
        assert -1e-9 <= f <= cap + 1e-9, f"Edge ({u}, {v}) flow {f} violates capacity {cap}"

    for node in graph.nodes():
        in_flow = sum(flow_map.get((u, node), 0.0) for u in graph.predecessors(node))
        out_flow = sum(flow_map.get((node, v), 0.0) for v in graph.successors(node))
        if node == source:
            assert pytest.approx(out_flow - in_flow, abs=1e-6) == reported_flow
        elif node == sink:
            assert pytest.approx(in_flow - out_flow, abs=1e-6) == reported_flow
        else:
            assert pytest.approx(in_flow, abs=1e-6) == out_flow, (
                f"Flow conservation violated at node {node}: in={in_flow}, out={out_flow}"
            )


def _assert_min_cut_matches_flow(graph: nx.DiGraph, min_cut_edges: list, max_flow: float):
    """Verify Max-Flow Min-Cut Theorem: sum of capacities on min-cut equals max_flow."""
    cut_cap = sum(
        float(graph[u][v].get("capacity", graph[u][v].get("weight", 1.0)))
        for u, v in min_cut_edges
    )
    assert pytest.approx(cut_cap, abs=1e-6) == max_flow


# ---------------------------------------------------------------------------
# 1. Graph Model & Scenario Loader Capacity Tests
# ---------------------------------------------------------------------------

def test_graph_model_supports_edge_capacity_and_updates():
    model = SpatialGraphModel()
    model.add_spatial_node(0, "Source", (0.0, 0.0))
    model.add_spatial_node(1, "Sink", (5.0, 0.0))
    model.add_weighted_edge(0, 1, weight=2.0, capacity=25.0)

    assert model.nx_graph[0][1]["weight"] == 2.0
    assert model.nx_graph[0][1]["capacity"] == 25.0

    old_cap = model.update_edge_capacity(0, 1, 8.0)
    assert old_cap == 25.0
    assert model.nx_graph[0][1]["capacity"] == 8.0

    topo = model.get_topology_dict()
    assert topo["edges"][0]["capacity"] == 8.0

    with pytest.raises(ValueError):
        model.update_edge_capacity(0, 1, -5.0)

    with pytest.raises(KeyError):
        model.update_edge_capacity(1, 0, 10.0)


def test_scenario_loader_loads_capacity_from_case_07():
    loader = ScenarioLoader(CASE_07_PATH)
    model = loader.build_graph_model()
    G = model.nx_graph

    assert G[0][1]["capacity"] == 20.0
    assert G[0][2]["capacity"] == 20.0
    assert G[1][3]["capacity"] == 15.0
    assert G[2][3]["capacity"] == 15.0
    assert G[1][2]["capacity"] == 5.0
    assert G[3][4]["capacity"] == 30.0


# ---------------------------------------------------------------------------
# 2. Registry & Inheritance Contract Tests
# ---------------------------------------------------------------------------

def test_maxflow_algorithms_registered_and_follow_ocp():
    from algorithms.maxflow.dinic import Dinic
    from algorithms.maxflow.ford_fulkerson import FordFulkerson

    assert issubclass(Dinic, FordFulkerson)
    assert FordFulkerson.SUPPORTED_EVENT_TYPES == frozenset({"DYNAMIC_EDGE_CAPACITY"})
    assert Dinic.SUPPORTED_EVENT_TYPES == frozenset({"DYNAMIC_EDGE_CAPACITY"})

    assert AlgorithmRegistry.resolve("ford_fulkerson") == "ford_fulkerson"
    assert AlgorithmRegistry.resolve("edmonds_karp") == "ford_fulkerson"
    assert AlgorithmRegistry.resolve("maxflow") == "ford_fulkerson"
    assert AlgorithmRegistry.resolve("dinic") == "dinic"


# ---------------------------------------------------------------------------
# 3. Core Max-Flow Correctness & Dynamic Events (Case 07)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("algo_key", ["ford_fulkerson", "dinic"])
def test_case_07_initial_and_dynamic_bottleneck(algo_key: str):
    loader = ScenarioLoader(CASE_07_PATH)
    model = loader.build_graph_model()
    plan = loader.get_execution_plan()

    solver = AlgorithmRegistry.create(algo_key, model)
    start, goal = plan["start_node"], plan["goal_node"]

    initial_flow = solver.run(start, goal)
    assert pytest.approx(initial_flow, abs=1e-6) == 30.0
    _assert_valid_flow(model.nx_graph, start, goal, solver.get_flow_distribution(), initial_flow)
    _assert_min_cut_matches_flow(model.nx_graph, solver.get_min_cut(), initial_flow)

    event = plan["events"][0]
    event_data = {
        "type": event["type"],
        "edge": tuple(event["target_edge"]),
        "new_capacity": event["new_capacity"],
        "start": start,
        "goal": goal,
    }
    post_flow = solver.handle_dynamic_event(event_data)
    assert pytest.approx(post_flow, abs=1e-6) == 4.0
    assert solver.get_min_cut() == [(3, 4)]
    _assert_valid_flow(model.nx_graph, start, goal, solver.get_flow_distribution(), post_flow)
    _assert_min_cut_matches_flow(model.nx_graph, solver.get_min_cut(), post_flow)

    assert solver.step_count > 0
    assert len(solver.delta_logs) == solver.step_count


# ---------------------------------------------------------------------------
# 4. Antiparallel (Two-Way Road) & Multi-Phase Dynamic Lifecycle Tests
# ---------------------------------------------------------------------------

def _build_two_way_road_network() -> SpatialGraphModel:
    """20-node two-way road network with parallel corridors & bottlenecks."""
    model = SpatialGraphModel()
    for i in range(20):
        model.add_spatial_node(i, f"Simpang_{i}", (float(i % 5) * 4.0, float(i // 5) * 4.0))

    # Main corridor + two alternative corridors + cross streets (antiparallel pairs)
    edges = [
        (0, 1, 25), (0, 5, 18), (0, 10, 15),
        (1, 2, 22), (2, 1, 10),
        (2, 3, 20), (3, 2, 10),
        (3, 4, 24),
        (5, 6, 16), (6, 5, 8),
        (6, 7, 15), (7, 6, 8),
        (7, 8, 16), (8, 9, 18),
        (10, 11, 14), (11, 12, 14), (12, 13, 14), (13, 14, 16),
        # Cross links (two-way)
        (1, 6, 10), (6, 1, 10),
        (2, 7, 12), (7, 2, 12),
        (3, 8, 10), (8, 3, 10),
        (6, 11, 9), (11, 6, 9),
        (7, 12, 10), (12, 7, 10),
        (8, 13, 9), (13, 8, 9),
        # Converging to sink area (nodes 15..19)
        (4, 15, 22), (9, 15, 14), (9, 16, 12), (14, 16, 15),
        (15, 16, 8), (16, 15, 8),
        (15, 17, 20), (16, 18, 20),
        (17, 18, 6), (18, 17, 6),
        (17, 19, 25), (18, 19, 25),
    ]
    for u, v, cap in edges:
        model.add_weighted_edge(u, v, weight=1.0, capacity=float(cap))
    return model


def test_20_node_two_way_network_dynamic_lifecycle_matches_networkx():
    """Verify Normal -> Total Closure (0) -> Partial Reopen -> Non-saturated Drop -> Capacity Boost."""
    model_ff = _build_two_way_road_network()
    model_dinic = _build_two_way_road_network()

    ff = AlgorithmRegistry.create("ford_fulkerson", model_ff)
    dinic = AlgorithmRegistry.create("dinic", model_dinic)

    source, sink = 0, 19

    # Phase 0: Normal
    f_ff = ff.run(source, sink)
    f_dinic = dinic.run(source, sink)
    expected = nx.maximum_flow_value(model_ff.nx_graph, source, sink, capacity="capacity")

    assert pytest.approx(f_ff, abs=1e-6) == expected
    assert pytest.approx(f_dinic, abs=1e-6) == expected
    _assert_valid_flow(model_ff.nx_graph, source, sink, ff.get_flow_distribution(), f_ff)
    _assert_valid_flow(model_dinic.nx_graph, source, sink, dinic.get_flow_distribution(), f_dinic)
    _assert_min_cut_matches_flow(model_ff.nx_graph, ff.get_min_cut(), f_ff)
    _assert_min_cut_matches_flow(model_dinic.nx_graph, dinic.get_min_cut(), f_dinic)

    # Sequence of dynamic events:
    # 1) Truk mogok tutup total di (2, 3)
    # 2) Petugas buka 1 lajur di (2, 3) -> 8
    # 3) Hambatan sekunder di (15, 17) -> 5
    # 4) Pemulihan penuh di (2, 3) -> 20
    # 5) Penurunan kecil pada edge yang longgar (17, 19) -> 22
    events = [
        ((2, 3), 0.0),
        ((2, 3), 8.0),
        ((15, 17), 5.0),
        ((2, 3), 20.0),
        ((17, 19), 22.0),
    ]

    for edge, new_cap in events:
        event_data = {
            "type": "DYNAMIC_EDGE_CAPACITY",
            "edge": edge,
            "new_capacity": new_cap,
            "start": source,
            "goal": sink,
        }
        r_ff = ff.handle_dynamic_event(event_data)
        r_dinic = dinic.handle_dynamic_event(event_data)
        expected = nx.maximum_flow_value(model_ff.nx_graph, source, sink, capacity="capacity")

        assert pytest.approx(r_ff, abs=1e-6) == expected
        assert pytest.approx(r_dinic, abs=1e-6) == expected
        _assert_valid_flow(model_ff.nx_graph, source, sink, ff.get_flow_distribution(), r_ff)
        _assert_valid_flow(model_dinic.nx_graph, source, sink, dinic.get_flow_distribution(), r_dinic)
        _assert_min_cut_matches_flow(model_dinic.nx_graph, dinic.get_min_cut(), r_dinic)


def test_randomized_stress_dynamic_updates_dinic_equals_networkx():
    """Stress-test Dinic incremental repair across 15 random 22-node graphs with antiparallel edges."""
    rng = random.Random(2026)

    for trial in range(15):
        n = 22
        model = SpatialGraphModel()
        for i in range(n):
            model.add_spatial_node(i, f"N{i}", (float(i), 0.0))

        edges_added = []
        for u in range(n - 1):
            # Forward spine ensures connectivity
            cap = float(rng.randint(5, 30))
            model.add_weighted_edge(u, u + 1, weight=1.0, capacity=cap)
            edges_added.append((u, u + 1))

        for _ in range(45):
            u = rng.randint(0, n - 1)
            v = rng.randint(0, n - 1)
            if u != v and not model.nx_graph.has_edge(u, v):
                cap = float(rng.randint(2, 25))
                model.add_weighted_edge(u, v, weight=1.0, capacity=cap)
                edges_added.append((u, v))

        dinic = AlgorithmRegistry.create("dinic", model)
        f0 = dinic.run(0, n - 1)
        exp0 = nx.maximum_flow_value(model.nx_graph, 0, n - 1, capacity="capacity")
        assert pytest.approx(f0, abs=1e-6) == exp0, f"Trial {trial} initial mismatch"
        _assert_valid_flow(model.nx_graph, 0, n - 1, dinic.get_flow_distribution(), f0)

        for step_idx in range(6):
            edge = rng.choice(edges_added)
            new_cap = float(rng.choice([0, 3, 10, 20, 35]))
            f_new = dinic.handle_dynamic_event({
                "type": "DYNAMIC_EDGE_CAPACITY",
                "edge": edge,
                "new_capacity": new_cap,
                "start": 0,
                "goal": n - 1,
            })
            exp_new = nx.maximum_flow_value(model.nx_graph, 0, n - 1, capacity="capacity")
            assert pytest.approx(f_new, abs=1e-6) == exp_new, (
                f"Trial {trial} step {step_idx} edge={edge} cap={new_cap}: got {f_new}, expected {exp_new}"
            )
            _assert_valid_flow(model.nx_graph, 0, n - 1, dinic.get_flow_distribution(), f_new)
            _assert_min_cut_matches_flow(model.nx_graph, dinic.get_min_cut(), f_new)


# ---------------------------------------------------------------------------
# 5. End-to-End Runner, Observers, Visualizer, & Benchmark Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("algo_key", ["ford_fulkerson", "dinic"])
def test_simulation_runner_and_observers_with_maxflow(algo_key: str, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("core.base_algorithm.OUTPUT_DIR", tmp_path)

    loader = ScenarioLoader(CASE_07_PATH)
    metadata = loader.get_metadata()
    plan = loader.get_execution_plan()
    model = loader.build_graph_model()

    solver = AlgorithmRegistry.create(algo_key, model)
    runner = SimulationRunner(solver=solver, plan=plan, metadata=metadata)
    runner.attach(ConsoleReportObserver())
    runner.attach(VisualizerSnapshotObserver(model.nx_graph))
    runner.attach(TraceExportObserver(solver))

    result = runner.execute()

    assert result.skipped_events == []
    assert pytest.approx(result.initial_cost, abs=1e-6) == 30.0
    assert len(result.reroutes) == 1
    assert pytest.approx(result.reroutes[0].cost, abs=1e-6) == 4.0
    assert result.reroutes[0].min_cut == [(3, 4)]

    expected_json = tmp_path / f"output_{metadata['case_id']}_{algo_key}.json"
    fallback_json = tmp_path / f"output_{metadata['case_id']}.json"
    assert expected_json.exists() or fallback_json.exists()


def test_benchmark_script_runs_both_maxflow_algorithms(capsys):
    from scripts.run_benchmark import main as benchmark_main

    benchmark_main([str(CASE_07_PATH), "--compare", "ford_fulkerson", "dinic"])
    captured = capsys.readouterr().out

    assert "FordFulkerson" in captured
    assert "Dinic" in captured
    assert "case_07_truk_mogok" in captured
