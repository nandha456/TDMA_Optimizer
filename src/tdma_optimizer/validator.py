"""Independent schedule verification.

The validator deliberately does **not** reuse the conflict graph H built by
``nx.power``. It recomputes "which pairs are within two hops" from the
communication graph G with a breadth-first search capped at depth 2. A bug in
conflict-graph construction or in the optimizer therefore cannot validate its
own output.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import networkx as nx

from tdma_optimizer.input_parser import natural_key


@dataclass(frozen=True)
class Violation:
    node_a: str
    node_b: str
    hops: int
    slot: int

    def describe(self) -> str:
        kind = "direct link" if self.hops == 1 else "hidden terminal (shared neighbor)"
        return f"{self.node_a} and {self.node_b} share slot {self.slot}: {kind}, {self.hops} hop(s)"


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: tuple[str, ...]
    violations: tuple[Violation, ...]
    pairs_checked: int


def pairs_within_two_hops(graph: nx.Graph) -> dict[tuple[str, str], int]:
    """Every unordered pair at hop distance 1 or 2, mapped to that distance.

    Keys are ordered naturally (``(Node_01, Node_03)``) so results are stable.
    """
    pairs: dict[tuple[str, str], int] = {}
    for source in graph.nodes:
        lengths = nx.single_source_shortest_path_length(graph, source, cutoff=2)
        for target, hops in lengths.items():
            if hops in (1, 2):
                key = tuple(sorted((source, target), key=natural_key))
                pairs[key] = hops  # type: ignore[index]
    return pairs


def validate_schedule(graph: nx.Graph, assignment: Mapping[str, object]) -> ValidationResult:
    """Check coverage, slot types, and every 1-hop and 2-hop pair. Never raises on bad data."""
    errors: list[str] = []
    nodes = set(graph.nodes)
    assigned = set(assignment)

    missing = sorted(nodes - assigned, key=natural_key)
    unknown = sorted(assigned - nodes, key=natural_key)
    if missing:
        errors.append(f"Nodes without a slot: {', '.join(missing)}")
    if unknown:
        errors.append(f"Slots assigned to unknown nodes: {', '.join(unknown)}")

    for node in sorted(assigned & nodes, key=natural_key):
        slot = assignment[node]
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
            errors.append(f"{node}: slot must be a non-negative integer, got {slot!r}")

    pairs = pairs_within_two_hops(graph)
    violations = []
    for (a, b), hops in sorted(pairs.items(), key=lambda kv: (natural_key(kv[0][0]), natural_key(kv[0][1]))):
        if a in assignment and b in assignment and assignment[a] == assignment[b]:
            violations.append(Violation(a, b, hops, assignment[a]))  # type: ignore[arg-type]
    errors.extend(v.describe() for v in violations)

    return ValidationResult(
        is_valid=not errors,
        errors=tuple(errors),
        violations=tuple(violations),
        pairs_checked=len(pairs),
    )
