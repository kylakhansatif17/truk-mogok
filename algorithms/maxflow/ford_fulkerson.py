from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from algorithms.registry import AlgorithmRegistry
from core.base_algorithm import BaseGraphAlgorithm
from core.graph_model import SpatialGraphModel

EPS = 1e-9


class FordFulkerson(BaseGraphAlgorithm):
    """Algoritma Dasar Maximum Flow (Ford-Fulkerson / Varian Edmonds-Karp BFS).

    Kompleksitas: O(V * E^2).
    Saat terjadi event perubahan kapasitas dinamis (DYNAMIC_EDGE_CAPACITY),
    algoritma klasik ini melakukan perhitungan ulang dari nol (full re-computation).
    """

    SUPPORTED_EVENT_TYPES = frozenset({"DYNAMIC_EDGE_CAPACITY"})
    METRIC_LABEL = "Max Flow"
    REGISTRY_KEY = "ford_fulkerson"

    def __init__(self, model: SpatialGraphModel):
        super().__init__(model)
        self.residual = nx.DiGraph()
        self.edge_capacities: Dict[Tuple[int, int], float] = {}
        self.edge_flows: Dict[Tuple[int, int], float] = {}
        self.last_max_flow: float = 0.0
        self.last_source: Optional[int] = None
        self.last_sink: Optional[int] = None
        self.min_cut_reachable: Set[int] = set()
        self.min_cut_edges: List[Tuple[int, int]] = []

    def _init_flow_network(self) -> None:
        """Membangun struktur kapasitas, aliran awal 0, dan residual graph."""
        self.residual.clear()
        self.edge_capacities.clear()
        self.edge_flows.clear()
        self.residual.add_nodes_from(self.graph.nodes())

        for u, v, data in self.graph.edges(data=True):
            cap = float(data.get("capacity", data.get("weight", 1.0)))
            self.edge_capacities[(u, v)] = cap
            self.edge_flows[(u, v)] = 0.0

        seen_pairs = set()
        for u, v in self.edge_capacities:
            pair = (u, v) if u <= v else (v, u)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                self._sync_residual_pair(u, v)

    def _sync_residual_pair(self, u: int, v: int) -> None:
        """Sinkronisasi kapasitas residual antara pasangan simpul (u, v) dan (v, u).

        Mendukung jalan dua arah (antiparallel edges) tanpa saling menimpa kapasitas.
        """
        cap_uv = self.edge_capacities.get((u, v), 0.0)
        cap_vu = self.edge_capacities.get((v, u), 0.0)
        flow_uv = self.edge_flows.get((u, v), 0.0)
        flow_vu = self.edge_flows.get((v, u), 0.0)

        res_uv = max(0.0, (cap_uv - flow_uv) + flow_vu)
        res_vu = max(0.0, (cap_vu - flow_vu) + flow_uv)

        self.residual.add_edge(u, v, capacity=res_uv)
        self.residual.add_edge(v, u, capacity=res_vu)

    def _push_along_residual_edge(self, u: int, v: int, delta: float) -> None:
        """Mendorong aliran delta pada edge residual (u -> v) dengan menjaga validitas antiparallel."""
        remaining = delta
        if (v, u) in self.edge_flows and self.edge_flows[(v, u)] > EPS:
            cancel = min(remaining, self.edge_flows[(v, u)])
            self.edge_flows[(v, u)] = max(0.0, self.edge_flows[(v, u)] - cancel)
            if self.edge_flows[(v, u)] <= EPS:
                self.edge_flows[(v, u)] = 0.0
            remaining -= cancel

        if remaining > EPS:
            if (u, v) not in self.edge_flows:
                raise RuntimeError(
                    f"Gagal mendorong aliran {remaining} pada edge non-eksisten ({u}, {v})."
                )
            new_flow = self.edge_flows[(u, v)] + remaining
            self.edge_flows[(u, v)] = min(self.edge_capacities[(u, v)], new_flow)

        self._sync_residual_pair(u, v)

    def _compute_min_cut(self, source_node: int) -> List[Tuple[int, int]]:
        """Menghitung Minimum Cut (S, T) berdasarkan simpul yang terjangkau dari source di residual graph."""
        reachable: Set[int] = {source_node}
        queue = deque([source_node])

        while queue:
            u = queue.popleft()
            for v in self.residual.neighbors(u):
                if v not in reachable and self.residual[u][v].get("capacity", 0.0) > EPS:
                    reachable.add(v)
                    queue.append(v)

        min_cut_edges = [
            (u, v)
            for u, v in self.graph.edges()
            if u in reachable and v not in reachable
        ]
        self.min_cut_reachable = reachable
        self.min_cut_edges = min_cut_edges
        return min_cut_edges

    def get_flow_distribution(self) -> Dict[Tuple[int, int], float]:
        """Mengembalikan peta distribusi aliran {(u, v): flow} pada graf asli."""
        return dict(self.edge_flows)

    def get_min_cut(self) -> List[Tuple[int, int]]:
        """Mengembalikan daftar edge bottleneck yang membentuk Minimum Cut."""
        return list(self.min_cut_edges)

    def get_min_cut_partitions(self) -> Tuple[List[int], List[int]]:
        """Mengembalikan partisi simpul (S, T) dari Minimum Cut."""
        s_nodes = sorted(self.min_cut_reachable)
        t_nodes = sorted(set(self.graph.nodes()) - self.min_cut_reachable)
        return s_nodes, t_nodes

    def _bfs(self, source: int, sink: int, parent: Dict[int, int]) -> bool:
        """Mencari shortest augmenting path (jumlah edge tersedikit) via BFS."""
        parent.clear()
        visited = {source}
        queue = deque([source])

        while queue:
            u = queue.popleft()
            for v in self.residual.neighbors(u):
                capacity = self.residual[u][v].get("capacity", 0.0)
                if v not in visited and capacity > EPS:
                    queue.append(v)
                    visited.add(v)
                    parent[v] = u
                    if v == sink:
                        return True
        return False

    def run(self, source_node: int, sink_node: int) -> float:
        self._init_flow_network()
        self.last_source = source_node
        self.last_sink = sink_node

        max_flow = 0.0
        parent: Dict[int, int] = {}

        self.log_step(
            event_type="INITIALIZATION",
            state_mutations={
                "algorithm": self.__class__.__name__,
                "source": source_node,
                "sink": sink_node,
                "max_flow": 0.0,
            },
        )

        while self._bfs(source_node, sink_node, parent):
            path_flow = float("inf")
            curr = sink_node
            while curr != source_node:
                prev = parent[curr]
                path_flow = min(path_flow, self.residual[prev][curr]["capacity"])
                curr = prev

            path = []
            curr = sink_node
            while curr != source_node:
                path.append(curr)
                curr = parent[curr]
            path.append(source_node)
            path.reverse()

            for i in range(len(path) - 1):
                self._push_along_residual_edge(path[i], path[i + 1], path_flow)

            max_flow += path_flow

            self.log_step(
                event_type="AUGMENTING_PATH_FOUND",
                state_mutations={
                    "path": path,
                    "flow_added": path_flow,
                    "current_max_flow": max_flow,
                },
            )

        self.last_max_flow = max_flow
        min_cut = self._compute_min_cut(source_node)
        min_cut_cap = sum(self.edge_capacities.get(e, 0.0) for e in min_cut)

        self.log_step(
            event_type="MAX_FLOW_FOUND",
            state_mutations={
                "max_flow": max_flow,
                "min_cut_edges": [list(e) for e in min_cut],
                "min_cut_capacity": min_cut_cap,
            },
        )

        return max_flow

    def handle_dynamic_event(self, event_data: Dict[str, Any]) -> float:
        """Menangani perubahan kapasitas edge dengan menghitung ulang penuh dari nol."""
        u, v = tuple(event_data["edge"])
        new_capacity = float(event_data["new_capacity"])
        source = event_data.get("source", event_data.get("start", self.last_source))
        sink = event_data.get("sink", event_data.get("goal", self.last_sink))

        old_capacity = self.model.update_edge_capacity(u, v, new_capacity)

        self.log_step(
            event_type="UPDATE_CAPACITY_EVENT",
            state_mutations={
                "target_edge": [u, v],
                "old_capacity": old_capacity,
                "new_capacity": new_capacity,
                "strategy": "FULL_RECOMPUTATION",
            },
        )

        return self.run(source, sink)


AlgorithmRegistry.register("ford_fulkerson", FordFulkerson)
AlgorithmRegistry.register_alias("edmonds_karp", "ford_fulkerson")
AlgorithmRegistry.register_alias("maxflow", "ford_fulkerson")
