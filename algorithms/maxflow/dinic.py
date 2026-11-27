from collections import deque
from typing import Any, Dict, List, Tuple

from algorithms.maxflow.ford_fulkerson import EPS, FordFulkerson
from algorithms.registry import AlgorithmRegistry


class Dinic(FordFulkerson):
    """Algoritma Lanjut (SOTA) Maximum Flow: Dinic's Algorithm + Incremental Residual Repair.

    Mewarisi FordFulkerson (Open/Closed Principle) dengan dua peningkatan utama:
    1. Pencarian awal memakai Level Graph (BFS) + Blocking Flow (DFS + current-arc pointer),
       menurunkan kompleksitas menjadi O(V^2 * E).
    2. Penanganan event dinamis (DYNAMIC_EDGE_CAPACITY) melakukan perbaikan residual
       secara inkremental tanpa membuang seluruh aliran yang sudah terbentuk.
    """

    REGISTRY_KEY = "dinic"

    def _build_level_graph(self, source: int, sink: int) -> Dict[int, int]:
        """Membangun Level Graph (jarak hop terpendek dari source) pada residual graph."""
        level: Dict[int, int] = {source: 0}
        queue = deque([source])

        while queue:
            u = queue.popleft()
            for v in self.residual.neighbors(u):
                if v not in level and self.residual[u][v].get("capacity", 0.0) > EPS:
                    level[v] = level[u] + 1
                    queue.append(v)

        return level

    def _dfs_blocking_flow(
        self,
        u: int,
        sink: int,
        pushed: float,
        level: Dict[int, int],
        adj: Dict[int, List[int]],
        ptr: Dict[int, int],
        path: List[int],
    ) -> Tuple[float, List[int]]:
        """Mendorong blocking flow dengan optimasi current-arc pointer (ptr)."""
        if pushed <= EPS or u == sink:
            return pushed, path + [u]

        neighbors = adj[u]
        while ptr[u] < len(neighbors):
            v = neighbors[ptr[u]]
            res_cap = self.residual[u][v].get("capacity", 0.0)
            if level.get(v) == level[u] + 1 and res_cap > EPS:
                tr, found_path = self._dfs_blocking_flow(
                    v, sink, min(pushed, res_cap), level, adj, ptr, path + [u]
                )
                if tr > EPS:
                    self._push_along_residual_edge(u, v, tr)
                    return tr, found_path
            ptr[u] += 1

        return 0.0, []

    def _augment_with_dinic(
        self,
        source: int,
        sink: int,
        limit: float = float("inf"),
        log_steps: bool = True,
        base_flow: float = 0.0,
    ) -> float:
        """Menjalankan loop Level Graph + Blocking Flow dari state residual saat ini."""
        total_added = 0.0
        phase = 0

        while total_added < limit - EPS:
            level = self._build_level_graph(source, sink)
            if sink not in level:
                break

            phase += 1
            if log_steps:
                self.log_step(
                    event_type="LEVEL_GRAPH_BUILT",
                    state_mutations={
                        "phase": phase,
                        "source": source,
                        "sink": sink,
                        "sink_level": level[sink],
                        "reachable_nodes": len(level),
                    },
                )

            adj = {node: list(self.residual.neighbors(node)) for node in self.residual.nodes()}
            ptr = {node: 0 for node in self.residual.nodes()}

            while total_added < limit - EPS:
                pushed, path = self._dfs_blocking_flow(
                    source, sink, limit - total_added, level, adj, ptr, []
                )
                if pushed <= EPS:
                    break

                total_added += pushed
                if log_steps:
                    self.log_step(
                        event_type="BLOCKING_FLOW_PUSHED",
                        state_mutations={
                            "phase": phase,
                            "path": path,
                            "flow_added": pushed,
                            "current_max_flow": base_flow + total_added,
                        },
                    )

        return total_added

    def _cancel_positive_flow(self, origin: int, destination: int, amount: float) -> float:
        """Membatalkan hingga `amount` unit aliran sepanjang jalur ber-aliran positif origin -> destination."""
        if origin == destination or amount <= EPS:
            return amount

        canceled_total = 0.0
        while canceled_total < amount - EPS:
            parent: Dict[int, int] = {}
            visited = {origin}
            queue = deque([origin])
            found = False

            while queue and not found:
                curr = queue.popleft()
                for nxt in self.graph.successors(curr):
                    if nxt not in visited and self.edge_flows.get((curr, nxt), 0.0) > EPS:
                        visited.add(nxt)
                        parent[nxt] = curr
                        if nxt == destination:
                            found = True
                            break
                        queue.append(nxt)

            if not found:
                break

            # Hitung bottleneck pada jalur ber-aliran positif
            bottleneck = amount - canceled_total
            node = destination
            while node != origin:
                prev = parent[node]
                bottleneck = min(bottleneck, self.edge_flows[(prev, node)])
                node = prev

            # Kurangi aliran sepanjang jalur dan sinkronkan residual graph
            node = destination
            while node != origin:
                prev = parent[node]
                self.edge_flows[(prev, node)] = max(
                    0.0, self.edge_flows[(prev, node)] - bottleneck
                )
                if self.edge_flows[(prev, node)] <= EPS:
                    self.edge_flows[(prev, node)] = 0.0
                self._sync_residual_pair(prev, node)
                node = prev

            canceled_total += bottleneck

        return canceled_total

    def run(self, source_node: int, sink_node: int) -> float:
        self._init_flow_network()
        self.last_source = source_node
        self.last_sink = sink_node
        self.last_max_flow = 0.0

        self.log_step(
            event_type="INITIALIZATION",
            state_mutations={
                "algorithm": self.__class__.__name__,
                "source": source_node,
                "sink": sink_node,
                "max_flow": 0.0,
            },
        )

        max_flow = self._augment_with_dinic(
            source_node, sink_node, limit=float("inf"), log_steps=True, base_flow=0.0
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
        """Perbaikan aliran inkremental pada residual graph tanpa menghitung ulang dari nol."""
        u, v = tuple(event_data["edge"])
        new_capacity = float(event_data["new_capacity"])
        source = event_data.get("source", event_data.get("start", self.last_source))
        sink = event_data.get("sink", event_data.get("goal", self.last_sink))

        old_capacity = self.model.update_edge_capacity(u, v, new_capacity)

        # Jika belum pernah dijalankan pada pasangan (source, sink) ini, jalankan dari awal
        if self.last_source != source or self.last_sink != sink or not self.edge_capacities:
            self.log_step(
                event_type="UPDATE_CAPACITY_EVENT",
                state_mutations={
                    "target_edge": [u, v],
                    "old_capacity": old_capacity,
                    "new_capacity": new_capacity,
                    "strategy": "COLD_START_DINIC",
                },
            )
            return self.run(source, sink)

        current_flow_uv = self.edge_flows.get((u, v), 0.0)
        self.edge_capacities[(u, v)] = new_capacity

        self.log_step(
            event_type="UPDATE_CAPACITY_EVENT",
            state_mutations={
                "target_edge": [u, v],
                "old_capacity": old_capacity,
                "new_capacity": new_capacity,
                "flow_on_edge_before": current_flow_uv,
                "strategy": "INCREMENTAL_RESIDUAL_REPAIR",
            },
        )

        # Kasus 1: Kapasitas bertambah -> dorong aliran tambahan langsung di residual graph
        if new_capacity >= old_capacity - EPS:
            self._sync_residual_pair(u, v)
            added = self._augment_with_dinic(
                source, sink, limit=float("inf"), log_steps=True, base_flow=self.last_max_flow
            )
            self.last_max_flow += added

        # Kasus 2: Kapasitas berkurang, tetapi masih >= aliran aktif pada edge (u, v)
        elif current_flow_uv <= new_capacity + EPS:
            self._sync_residual_pair(u, v)
            self.log_step(
                event_type="INCREMENTAL_NO_RECOMPUTE",
                state_mutations={
                    "target_edge": [u, v],
                    "active_flow": current_flow_uv,
                    "new_capacity": new_capacity,
                    "current_max_flow": self.last_max_flow,
                },
            )

        # Kasus 3: Kapasitas berkurang di bawah aliran aktif -> local reroute + partial cancel
        else:
            excess = current_flow_uv - new_capacity
            self.edge_flows[(u, v)] = new_capacity
            self._sync_residual_pair(u, v)

            # 3a. Coba alihkan aliran secara lokal dari u ke v pada residual graph
            rerouted = self._augment_with_dinic(
                u, v, limit=excess, log_steps=False
            )
            remaining_excess = max(0.0, excess - rerouted)

            if rerouted > EPS:
                self.log_step(
                    event_type="LOCAL_REROUTE_REPAIR",
                    state_mutations={
                        "target_edge": [u, v],
                        "excess": excess,
                        "rerouted_locally": rerouted,
                        "remaining_excess": remaining_excess,
                    },
                )

            # 3b. Batalkan sisa kelebihan aliran hanya pada jalur terdampak (s->u dan v->t)
            if remaining_excess > EPS:
                self._cancel_positive_flow(source, u, remaining_excess)
                self._cancel_positive_flow(v, sink, remaining_excess)
                self.last_max_flow = max(0.0, self.last_max_flow - remaining_excess)

                self.log_step(
                    event_type="PARTIAL_FLOW_CANCELED",
                    state_mutations={
                        "target_edge": [u, v],
                        "canceled_flow": remaining_excess,
                        "current_max_flow": self.last_max_flow,
                    },
                )

                # 3c. Lanjutkan Dinic di residual graph untuk menangkap jalur pengganti s->t
                recovered = self._augment_with_dinic(
                    source,
                    sink,
                    limit=float("inf"),
                    log_steps=True,
                    base_flow=self.last_max_flow,
                )
                self.last_max_flow += recovered

        min_cut = self._compute_min_cut(source)
        min_cut_cap = sum(self.edge_capacities.get(e, 0.0) for e in min_cut)

        self.log_step(
            event_type="MAX_FLOW_FOUND",
            state_mutations={
                "max_flow": self.last_max_flow,
                "min_cut_edges": [list(e) for e in min_cut],
                "min_cut_capacity": min_cut_cap,
            },
        )

        return self.last_max_flow


AlgorithmRegistry.register("dinic", Dinic)
