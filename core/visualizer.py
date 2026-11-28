import math
import textwrap
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import networkx as nx


class SimpleGraphVisualizer:

    def __init__(self, graph: nx.DiGraph):
        self.graph = graph
        # Ambil posisi node dari attribute 'pos' di YAML
        raw_pos = nx.get_node_attributes(graph, "pos")
        # Jika pos tidak didefinisikan, gunakan spring layout otomatis
        if not raw_pos:
            raw_pos = nx.spring_layout(graph, seed=42)
        self.pos = (
            self._spread_overlapping_positions(raw_pos)
            if len(graph.nodes) >= 15
            else raw_pos
        )

    @staticmethod
    def _spread_overlapping_positions(
        raw_pos: Dict[int, Tuple[float, float]],
        min_dist: float = 1.15,
        edge_min_dist: float = 1.35,
        iterations: int = 240,
    ) -> Dict[int, Tuple[float, float]]:
        """Merenggangkan node & edge yang terlalu rapat agar label tidak bertabrakan."""
        nodes = list(raw_pos.keys())
        if len(nodes) < 2:
            return dict(raw_pos)

        xs = [float(raw_pos[n][0]) for n in nodes]
        ys = [float(raw_pos[n][1]) for n in nodes]
        span_x = max(xs) - min(xs) or 1.0
        span_y = max(ys) - min(ys) or 1.0
        scale = 10.0 / max(span_x, span_y)

        pos = {
            n: [(float(raw_pos[n][0]) - min(xs)) * scale, (float(raw_pos[n][1]) - min(ys)) * scale]
            for n in nodes
        }

        for _ in range(iterations):
            moved = False
            for i in range(len(nodes)):
                u = nodes[i]
                for j in range(i + 1, len(nodes)):
                    v = nodes[j]
                    dx = pos[v][0] - pos[u][0]
                    dy = pos[v][1] - pos[u][1]
                    dist = math.hypot(dx, dy)
                    if dist < min_dist:
                        moved = True
                        if dist < 1e-6:
                            dx, dy, dist = 1.0, 0.2, math.hypot(1.0, 0.2)
                        push = 0.5 * (min_dist - dist) / dist
                        pos[u][0] -= dx * push
                        pos[u][1] -= dy * push
                        pos[v][0] += dx * push
                        pos[v][1] += dy * push
            if not moved:
                break

        return {n: (coords[0], coords[1]) for n, coords in pos.items()}

    @staticmethod
    def _is_headless_backend() -> bool:
        return matplotlib.get_backend().lower() in {"agg", "pdf", "ps", "svg", "template"}

    def draw_snapshot(
        self,
        title: str,
        active_path: Optional[List[int]] = None,
        highlighted_edge: Optional[Tuple[int, int]] = None,
        flow_distribution: Optional[Dict[Tuple[int, int], float]] = None,
        min_cut_edges: Optional[List[Tuple[int, int]]] = None,
        save_path: Optional[Path] = None,
        show: bool = True,
    ):
        """Menggambar snapshot kondisi graf (mendukung Pathfinding maupun Maximum Flow)."""
        num_nodes = len(self.graph.nodes)
        use_legend_table = num_nodes >= 15

        if use_legend_table:
            fig, (ax, ax_table) = plt.subplots(
                1,
                2,
                figsize=(20, 10),
                gridspec_kw={"width_ratios": [2.0, 1.0]},
            )
            node_size = 330
            font_size = 6.5
            node_labels = {node: str(node) for node in self.graph.nodes()}
        else:
            fig, ax = plt.subplots(figsize=(9, 5.5))
            ax_table = None
            node_size = 700
            font_size = 8
            node_labels = {
                node: f"{node}\n({data.get('label', '')})"
                for node, data in self.graph.nodes(data=True)
            }

        ax.set_title(textwrap.fill(title, width=82), fontsize=10.5, fontweight="bold", pad=10)

        # 1. Gambar Semua Node
        nx.draw_networkx_nodes(
            self.graph,
            self.pos,
            ax=ax,
            node_size=node_size,
            node_color="lightblue",
            edgecolors="black",
        )

        nx.draw_networkx_labels(
            self.graph,
            self.pos,
            labels=node_labels,
            font_size=font_size + (1 if use_legend_table else 0),
            font_weight="bold" if use_legend_table else "normal",
            ax=ax,
        )

        # 2. Mode Maximum Flow vs Mode Pathfinding
        if flow_distribution is not None:
            self._draw_maxflow_edges(ax, flow_distribution, min_cut_edges, highlighted_edge, font_size)
        else:
            self._draw_pathfinding_edges(ax, active_path, highlighted_edge, font_size)

        ax.margins(x=0.14 if use_legend_table else 0.18, y=0.14 if use_legend_table else 0.16)
        ax.axis("off")

        if ax_table is not None:
            self._draw_node_table(ax_table)

        fig.tight_layout()

        if save_path is not None:
            fig.savefig(save_path, dpi=150, bbox_inches="tight")

        if show and not self._is_headless_backend():
            plt.show()
        else:
            plt.close(fig)

    def _draw_node_table(self, ax_table) -> None:
        """Menampilkan tabel pemetaan nomor node ke nama jalan di panel samping."""
        ax_table.axis("off")
        ax_table.set_title("Keterangan Simpul (Node)", fontsize=10, fontweight="bold", pad=8)

        sorted_nodes = sorted(self.graph.nodes(data=True), key=lambda item: item[0])
        rows = []
        for node, data in sorted_nodes:
            label = str(data.get("label", "")).strip() or "-"
            rows.append([str(node), label])

        table = ax_table.table(
            cellText=rows,
            colLabels=["Node", "Lokasi / Nama Jalan"],
            colWidths=[0.13, 0.87],
            loc="center",
            cellLoc="left",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(7.5)
        table.scale(1.0, 1.35)

        for (row_idx, col_idx), cell in table.get_celld().items():
            cell.set_edgecolor("#cfd8dc")
            if row_idx == 0:
                cell.set_facecolor("#1e88e5")
                cell.set_text_props(color="white", weight="bold")
            else:
                cell.set_facecolor("#f8fafc" if row_idx % 2 == 1 else "#ffffff")
                if col_idx == 0:
                    cell.set_text_props(weight="bold", ha="center")

    def _draw_pathfinding_edges(
        self,
        ax,
        active_path: Optional[List[int]],
        highlighted_edge: Optional[Tuple[int, int]],
        font_size: int,
    ) -> None:
        nx.draw_networkx_edges(
            self.graph,
            self.pos,
            ax=ax,
            edgelist=list(self.graph.edges()),
            edge_color="gray",
            arrows=True,
            arrowsize=15,
        )

        edge_labels = nx.get_edge_attributes(self.graph, "weight")
        nx.draw_networkx_edge_labels(
            self.graph, self.pos, edge_labels=edge_labels, font_size=font_size + 1, ax=ax
        )

        if highlighted_edge:
            nx.draw_networkx_edges(
                self.graph,
                self.pos,
                ax=ax,
                edgelist=[highlighted_edge],
                edge_color="red",
                width=3,
                arrows=True,
                arrowsize=20,
            )

        if active_path and len(active_path) > 1:
            path_edges = list(zip(active_path[:-1], active_path[1:]))
            nx.draw_networkx_edges(
                self.graph,
                self.pos,
                ax=ax,
                edgelist=path_edges,
                edge_color="green",
                width=4,
                arrows=True,
                arrowsize=20,
            )

    def _draw_maxflow_edges(
        self,
        ax,
        flow_distribution: Dict[Tuple[int, int], float],
        min_cut_edges: Optional[List[Tuple[int, int]]],
        highlighted_edge: Optional[Tuple[int, int]],
        font_size: int,
    ) -> None:
        min_cut_set = set(min_cut_edges or [])
        all_edges = list(self.graph.edges())

        inactive_edges = [
            e for e in all_edges
            if flow_distribution.get(e, 0.0) <= 1e-9
            and e not in min_cut_set
            and e != highlighted_edge
        ]
        active_edges = [
            e for e in all_edges
            if flow_distribution.get(e, 0.0) > 1e-9
            and e not in min_cut_set
            and e != highlighted_edge
        ]

        if inactive_edges:
            nx.draw_networkx_edges(
                self.graph,
                self.pos,
                ax=ax,
                edgelist=inactive_edges,
                edge_color="#b0bec5",
                width=1.2,
                arrows=True,
                arrowsize=12,
                connectionstyle="arc3,rad=0.06",
            )

        if active_edges:
            nx.draw_networkx_edges(
                self.graph,
                self.pos,
                ax=ax,
                edgelist=active_edges,
                edge_color="#1e88e5",
                width=2.6,
                arrows=True,
                arrowsize=16,
                connectionstyle="arc3,rad=0.06",
            )

        cut_only = [e for e in min_cut_set if e != highlighted_edge]
        if cut_only:
            nx.draw_networkx_edges(
                self.graph,
                self.pos,
                ax=ax,
                edgelist=cut_only,
                edge_color="#ef6c00",
                style="dashed",
                width=3.2,
                arrows=True,
                arrowsize=18,
                connectionstyle="arc3,rad=0.06",
            )

        if highlighted_edge and self.graph.has_edge(*highlighted_edge):
            nx.draw_networkx_edges(
                self.graph,
                self.pos,
                ax=ax,
                edgelist=[highlighted_edge],
                edge_color="#d32f2f",
                width=3.8,
                arrows=True,
                arrowsize=20,
                connectionstyle="arc3,rad=0.06",
            )

        edge_labels = {}
        compact_labels = len(self.graph.nodes) >= 15
        seen_pairs = set()

        for u, v, data in self.graph.edges(data=True):
            cap = float(data.get("capacity", data.get("weight", 1.0)))
            flow = float(flow_distribution.get((u, v), 0.0))

            if compact_labels and self.graph.has_edge(v, u):
                pair = (min(u, v), max(u, v))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                rev_cap = float(self.graph[v][u].get("capacity", self.graph[v][u].get("weight", 1.0)))
                rev_flow = float(flow_distribution.get((v, u), 0.0))

                if flow > 1e-9 and rev_flow <= 1e-9:
                    edge_labels[(u, v)] = f"{flow:g}/{cap:g}"
                elif rev_flow > 1e-9 and flow <= 1e-9:
                    edge_labels[(v, u)] = f"{rev_flow:g}/{rev_cap:g}"
                elif flow > 1e-9 and rev_flow > 1e-9:
                    edge_labels[(u, v)] = f"{flow:g}/{cap:g}"
                    edge_labels[(v, u)] = f"{rev_flow:g}/{rev_cap:g}"
                elif (u, v) in min_cut_set or (u, v) == highlighted_edge:
                    edge_labels[(u, v)] = f"0/{cap:g}"
                elif (v, u) in min_cut_set or (v, u) == highlighted_edge:
                    edge_labels[(v, u)] = f"0/{rev_cap:g}"
                else:
                    edge_labels[(u, v)] = f"0/{cap:g}"
            else:
                edge_labels[(u, v)] = f"{flow:g}/{cap:g}"

        nx.draw_networkx_edge_labels(
            self.graph,
            self.pos,
            edge_labels=edge_labels,
            font_size=5.8 if compact_labels else font_size,
            label_pos=0.5 if compact_labels else 0.35,
            rotate=not compact_labels,
            bbox={"boxstyle": "round,pad=0.1", "fc": "white", "ec": "#e0e0e0", "alpha": 0.9}
            if compact_labels
            else None,
            ax=ax,
        )

        legend_items = [
            Line2D([0], [0], color="#1e88e5", lw=2.6, label="Aliran Aktif (flow/cap)"),
            Line2D([0], [0], color="#b0bec5", lw=1.2, label="Tidak Terpakai (0/cap)"),
            Line2D([0], [0], color="#ef6c00", lw=3.2, ls="--", label="Min-Cut (Bottleneck)"),
            Line2D([0], [0], color="#d32f2f", lw=3.8, label="Edge Gangguan (Event)"),
        ]
        ax.legend(handles=legend_items, loc="upper left", fontsize=8, framealpha=0.9)
