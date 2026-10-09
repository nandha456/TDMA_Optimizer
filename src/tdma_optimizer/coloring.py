"""Heuristic slot minimisation: greedy coloring of the conflict graph H.

Search plan (all deterministic for a given seed):

1. Deterministic greedy orders from NetworkX, DSATUR first as the baseline.
2. ``restarts`` random vertex orders (first-fit greedy), from a seeded
   :class:`random.Random` so results are reproducible.
3. Iterated-greedy refinement (Culberson) of the best coloring: re-run greedy
   with each color class kept contiguous. This can never increase the slot
   count, so it is a safe local improvement step.

The best *valid* coloring wins; ties keep the earliest attempt, so DSATUR is
preferred when nothing beats it.
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import networkx as nx

BASELINE_STRATEGY = "saturation_largest_first"
DETERMINISTIC_STRATEGIES: tuple[str, ...] = (
    BASELINE_STRATEGY,  # DSATUR
    "largest_first",
    "smallest_last",
    "independent_set",
    "connected_sequential_bfs",
    "connected_sequential_dfs",
)
DEFAULT_SEED = 42
DEFAULT_RESTARTS = 100
DEFAULT_REFINE_PASSES = 50

Coloring = dict[str, int]


@dataclass(frozen=True)
class AttemptSummary:
    """Slot counts produced by one heuristic (``runs`` > 1 for randomized ones)."""

    method: str
    runs: int
    best: int
    worst: int
    mean: float


@dataclass(frozen=True)
class HeuristicResult:
    """Best coloring found by the heuristics, plus the evidence of how it was found."""

    assignment: Coloring  # normalized: slots are 0..num_slots-1
    num_slots: int
    method: str
    attempts: tuple[AttemptSummary, ...]
    seed: int
    restarts: int


def count_slots(coloring: Coloring) -> int:
    """Number of distinct slots used."""
    return len(set(coloring.values()))


def is_proper(graph: nx.Graph, coloring: Coloring) -> bool:
    """Every node colored and no edge joins two equal colors."""
    if set(coloring) != set(graph.nodes):
        return False
    return all(coloring[u] != coloring[v] for u, v in graph.edges)


def normalize_slots(coloring: Coloring, node_order: Iterable[str]) -> Coloring:
    """Relabel slots to 0..K-1 in order of first appearance along ``node_order``.

    A relabeling is a bijection on colors, so every pair that differed still
    differs: conflict relationships are untouched. It makes output stable and
    readable (the first node always gets slot 0).
    """
    relabel: dict[int, int] = {}
    normalized: Coloring = {}
    for node in node_order:
        color = coloring[node]
        if color not in relabel:
            relabel[color] = len(relabel)
        normalized[node] = relabel[color]
    return normalized


def _fixed_order(order: Sequence[str]) -> Callable[[nx.Graph, dict], Iterable[str]]:
    """Wrap an explicit vertex order as a NetworkX greedy strategy."""
    return lambda _graph, _colors: iter(order)


def greedy_in_order(graph: nx.Graph, order: Sequence[str]) -> Coloring:
    """First-fit greedy: each node takes the smallest slot unused by its colored neighbors."""
    return nx.coloring.greedy_color(graph, strategy=_fixed_order(order))


def iterated_greedy(
    graph: nx.Graph, coloring: Coloring, rng: random.Random, passes: int
) -> Coloring:
    """Culberson's iterated greedy refinement.

    Re-coloring greedily in an order where every color class is contiguous
    yields at most as many colors as before (each class stays independent, so
    it can always reuse a color no larger than its old one). Class order is
    varied per pass (reverse, largest-first, random) to escape plateaus.
    """
    current = coloring
    for index in range(passes):
        classes: dict[int, list[str]] = {}
        for node in graph.nodes:  # graph order keeps this deterministic
            classes.setdefault(current[node], []).append(node)
        groups = list(classes.values())
        mode = index % 3
        if mode == 0:
            groups.reverse()
        elif mode == 1:
            groups.sort(key=len, reverse=True)
        else:
            rng.shuffle(groups)
        candidate = greedy_in_order(graph, [n for group in groups for n in group])
        if count_slots(candidate) <= count_slots(current):
            current = candidate
    return current


def optimize_schedule(
    conflict_graph: nx.Graph,
    *,
    seed: int = DEFAULT_SEED,
    restarts: int = DEFAULT_RESTARTS,
    refine_passes: int = DEFAULT_REFINE_PASSES,
) -> HeuristicResult:
    """Run every heuristic and return the valid coloring with the fewest slots."""
    if restarts < 0 or refine_passes < 0:
        raise ValueError("restarts and refine_passes must be non-negative")

    nodes = list(conflict_graph.nodes)
    best: Coloring | None = None
    best_method = ""
    attempts: list[AttemptSummary] = []

    def consider(candidate: Coloring, method: str) -> None:
        nonlocal best, best_method
        if not is_proper(conflict_graph, candidate):  # keep only valid solutions
            return
        if best is None or count_slots(candidate) < count_slots(best):
            best, best_method = candidate, method

    for strategy in DETERMINISTIC_STRATEGIES:
        candidate = nx.coloring.greedy_color(conflict_graph, strategy=strategy)
        consider(candidate, strategy)
        k = count_slots(candidate)
        attempts.append(AttemptSummary(strategy, 1, k, k, float(k)))

    rng = random.Random(seed)
    if restarts:
        counts = []
        label = f"random_order (seed={seed})"
        for _ in range(restarts):
            order = nodes[:]
            rng.shuffle(order)
            candidate = greedy_in_order(conflict_graph, order)
            consider(candidate, label)
            counts.append(count_slots(candidate))
        attempts.append(
            AttemptSummary(label, restarts, min(counts), max(counts), statistics.fmean(counts))
        )

    assert best is not None or not nodes
    best = best or {}

    if refine_passes and nodes:
        refined = iterated_greedy(conflict_graph, best, rng, refine_passes)
        k = count_slots(refined)
        attempts.append(AttemptSummary("iterated_greedy refinement", refine_passes, k, k, k))
        if is_proper(conflict_graph, refined) and k < count_slots(best):
            best, best_method = refined, f"{best_method} + iterated_greedy"

    normalized = normalize_slots(best, nodes)
    return HeuristicResult(
        assignment=normalized,
        num_slots=count_slots(normalized),
        method=best_method,
        attempts=tuple(attempts),
        seed=seed,
        restarts=restarts,
    )
