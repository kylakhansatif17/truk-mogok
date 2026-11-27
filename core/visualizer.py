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
        self.pos = nx.get_node_attributes(graph, "pos")
        # Jika pos tidak didefinisikan, gunakan spring layout otomatis
        if not self.pos:
            self.pos = nx.spring_layout(graph, seed=42)

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
        figsize = (13, 8) if num_nodes >= 15 else (9, 5.5)
        node_size = 500 if num_nodes >= 15 else 700
        font_size = 7 if num_nodes >= 15 else 8

        fig, ax = plt.subplots(figsize=figsize)
        ax.set_title(title, fontsize=11, fontweight="bold")

        # 1. Gambar Semua Node
        nx.draw_networkx_nodes(
            self.graph,
            self.pos,
            ax=ax,
            node_size=node_size,
            node_color="lightblue",
            edgecolors="black",
        )

        node_labels = {
            node: f"{node}\n({data.get('label', '')})"
            for node, data in self.graph.nodes(data=True)
        }
        nx.draw_networkx_labels(
            self.graph, self.pos, labels=node_labels, font_size=font_size, ax=ax
        )

        # 2. Mode Maximum Flow vs Mode Pathfinding
        if flow_distribution is not None:
            self._draw_maxflow_edges(ax, flow_distribution, min_cut_edges, highlighted_edge, font_size)
        else:
            self._draw_pathfinding_edges(ax, active_path, highlighted_edge, font_size)

        ax.margins(x=0.18, y=0.16)
        ax.axis("off")
        fig.tight_layout()

        if save_path is not None:
            fig.savefig(save_path, dpi=150, bbox_inches="tight")

        if show and not self._is_headless_backend():
            plt.show()
        else:
            plt.close(fig)

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
        for u, v, data in self.graph.edges(data=True):
            cap = float(data.get("capacity", data.get("weight", 1.0)))
            flow = float(flow_distribution.get((u, v), 0.0))
            edge_labels[(u, v)] = f"{flow:g}/{cap:g}"

        nx.draw_networkx_edge_labels(
            self.graph,
            self.pos,
            edge_labels=edge_labels,
            font_size=font_size,
            label_pos=0.35,
            ax=ax,
        )

        legend_items = [
            Line2D([0], [0], color="#1e88e5", lw=2.6, label="Aliran Aktif (flow/cap)"),
            Line2D([0], [0], color="#b0bec5", lw=1.2, label="Tidak Terpakai (0/cap)"),
            Line2D([0], [0], color="#ef6c00", lw=3.2, ls="--", label="Min-Cut (Bottleneck)"),
            Line2D([0], [0], color="#d32f2f", lw=3.8, label="Edge Gangguan (Event)"),
        ]
        ax.legend(handles=legend_items, loc="upper left", fontsize=8, framealpha=0.9)
