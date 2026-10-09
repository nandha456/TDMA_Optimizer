"""Lower bounds and bounded exact search: can we *prove* the slot count is minimal?

Minimum graph coloring is NP-hard, so heuristics alone cannot claim optimality.
Two cheap tools let us certify it anyway on networks of this size:

* **Clique lower bound.** Every pair inside a clique of H conflicts, so a
  clique of size w needs w distinct slots: chi(H) >= w. In G^2 the closed
  neighborhood of any radio is a clique, so w >= max_degree(G) + 1. If the
  heuristic hits w, it is optimal, with the clique as the witness.

* **Bounded branch-and-bound (DSATUR order).** If a gap remains, search for a
  coloring with fewer slots than the incumbent. The witness clique is
  pre-colored 0..w-1 (symmetry breaking), then nodes are branched in DSATUR
  order. Stops when (a) it finds a coloring that meets the lower bound,
  (b) the tree is exhausted: the incumbent is proven optimal, or
  (c) ``node_budget`` search nodes are spent: result is reported as heuristic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import networkx as nx

from tdma_optimizer.coloring import Coloring, count_slots, normalize_slots
from tdma_optimizer.input_parser import natural_key

DEFAULT_NODE_BUDGET = 200_000
# Recursion depth equals the number of radios; stay well under Python's limit.
MAX_EXACT_GRAPH_SIZE = 400


class Optimality(Enum):
    PROVEN_BY_CLIQUE = "proven optimal: equals clique lower bound"
    PROVEN_BY_SEARCH = "proven optimal: exhaustive branch-and-bound"
    HEURISTIC = "best found (optimality not proven)"


@dataclass(frozen=True)
class ExactResult:
    assignment: Coloring
    num_slots: int
    lower_bound: int
    clique_witness: tuple[str, ...]
    optimality: Optimality
    search_nodes: int
    improved: bool  # did the exact search beat the heuristic?


class _BudgetExhausted(Exception):
    pass


def clique_lower_bound(conflict_graph: nx.Graph) -> tuple[int, tuple[str, ...]]:
    """Size and members of a maximum clique of H (deterministic tie-break).

    Enumerates maximal cliques (Bron-Kerbosch). Exponential in the worst case
    but immediate for geometric graphs of tens to hundreds of nodes.
    """
    if conflict_graph.number_of_nodes() == 0:
        return 0, ()
    best: tuple[str, ...] = ()
    for clique in nx.find_cliques(conflict_graph):
        members = tuple(sorted(clique, key=natural_key))
        if len(members) > len(best) or (
            len(members) == len(best) and [natural_key(m) for m in members] < [natural_key(m) for m in best]
        ):
            best = members
    return len(best), best


def _branch_and_bound(
    graph: nx.Graph,
    incumbent: Coloring,
    lower_bound: int,
    witness: tuple[str, ...],
    node_budget: int,
) -> tuple[Coloring, bool, int]:
    """Return (best coloring, proven_optimal, search nodes used)."""
    best = dict(incumbent)
    best_k = count_slots(best)
    colors: Coloring = {node: slot for slot, node in enumerate(witness)}
    order_index = {node: i for i, node in enumerate(graph.nodes)}
    explored = 0

    def pick_node() -> str:
        # DSATUR: most distinct neighbor colors, then most uncolored neighbors,
        # then graph (natural) order. Deterministic.
        def score(v: str) -> tuple[int, int, int]:
            saturation = len({colors[u] for u in graph[v] if u in colors})
            uncolored = sum(1 for u in graph[v] if u not in colors)
            return (saturation, uncolored, -order_index[v])

        return max((v for v in graph.nodes if v not in colors), key=score)

    def search(used: int) -> bool:
        """True when a coloring meeting the lower bound is found (stop early)."""
        nonlocal best, best_k, explored
        explored += 1
        if explored > node_budget:
            raise _BudgetExhausted
        if len(colors) == graph.number_of_nodes():
            best, best_k = dict(colors), used
            return best_k <= lower_bound
        v = pick_node()
        forbidden = {colors[u] for u in graph[v] if u in colors}
        color = 0
        # Only colors that keep the total strictly below the incumbent are worth trying;
        # best_k shrinks as better colorings are found.
        while color <= used and color < best_k - 1:
            if color not in forbidden:
                colors[v] = color
                if search(max(used, color + 1)):
                    return True
                del colors[v]
            color += 1
        return False

    try:
        search(len(witness))
    except _BudgetExhausted:
        return best, False, node_budget
    return best, True, explored


def certify(
    conflict_graph: nx.Graph,
    heuristic_assignment: Coloring,
    node_budget: int = DEFAULT_NODE_BUDGET,
) -> ExactResult:
    """Compare the heuristic against the lower bound and, if needed, search for better.

    ``node_budget = 0`` disables the search (the bound is still reported).
    """
    k = count_slots(heuristic_assignment)
    lower, witness = clique_lower_bound(conflict_graph)

    if k <= lower:
        return ExactResult(heuristic_assignment, k, lower, witness,
                           Optimality.PROVEN_BY_CLIQUE, 0, improved=False)

    if node_budget <= 0 or conflict_graph.number_of_nodes() > MAX_EXACT_GRAPH_SIZE:
        return ExactResult(heuristic_assignment, k, lower, witness,
                           Optimality.HEURISTIC, 0, improved=False)

    found, proven, explored = _branch_and_bound(
        conflict_graph, heuristic_assignment, lower, witness, node_budget
    )
    found = normalize_slots(found, conflict_graph.nodes)
    found_k = count_slots(found)
    if found_k <= lower:
        optimality = Optimality.PROVEN_BY_CLIQUE
    elif proven:
        optimality = Optimality.PROVEN_BY_SEARCH
    else:
        optimality = Optimality.HEURISTIC
    return ExactResult(found, found_k, lower, witness, optimality, explored,
                       improved=found_k < k)
