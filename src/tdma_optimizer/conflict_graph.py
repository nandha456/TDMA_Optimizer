"""Build the conflict graph H = G^2 (distance-2 interference).

Why not color G directly?  A proper coloring of G only separates *neighbors*.
In the chain ``A -- B -- C``, A and C are not neighbors, so coloring G may give
them the same slot. Both then transmit while B listens, and their signals
collide at B: the hidden-terminal problem. Distance-2 coloring of G is exactly
ordinary coloring of G^2, where u and v are adjacent iff their hop distance in
G is 1 or 2. Nodes 3+ hops apart stay non-adjacent in H, which is what permits
spatial reuse.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


@dataclass(frozen=True)
class ConflictStats:
    """Breakdown of conflict-graph edges by the interference type that caused them."""

    total: int
    one_hop: int  # direct-link interference (also edges of G)
    two_hop: int  # hidden-terminal interference only (shared neighbor, not linked)


def build_conflict_graph(communication_graph: nx.Graph) -> nx.Graph:
    """Return H = G^2 with edge attribute ``hops`` in {1, 2}.

    ``nx.power`` keeps G's node order but not its attributes, so positions are
    copied back for downstream consumers.
    """
    conflict = nx.power(communication_graph, 2)
    for node, data in communication_graph.nodes(data=True):
        conflict.nodes[node].update(data)
    for u, v in conflict.edges:
        conflict.edges[u, v]["hops"] = 1 if communication_graph.has_edge(u, v) else 2
    return conflict


def conflict_stats(conflict_graph: nx.Graph) -> ConflictStats:
    """Count 1-hop and 2-hop-only conflict edges."""
    one_hop = sum(1 for *_, hops in conflict_graph.edges(data="hops") if hops == 1)
    total = conflict_graph.number_of_edges()
    return ConflictStats(total=total, one_hop=one_hop, two_hop=total - one_hop)
