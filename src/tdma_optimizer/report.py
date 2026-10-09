"""Human-readable ASCII report: statistics, node->slot mapping, Slot x Node matrix.

Both schedule representations are generated from the same assignment
dictionary, so they cannot disagree.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence

from tdma_optimizer.coloring import BASELINE_STRATEGY
from tdma_optimizer.pipeline import SchedulePlan

WIDTH = 72
DEFAULT_SLOT_MS = 1.0  # slot length requested for the EMANE part of the assessment


def build_slot_matrix(assignment: Mapping[str, int], node_order: Sequence[str]) -> list[list[int]]:
    """Rows = slots 0..K-1, columns = ``node_order``; 1 where the node transmits.

    Each column contains exactly one 1 because each node has exactly one slot.
    """
    num_slots = max(assignment.values(), default=-1) + 1
    return [[1 if assignment[node] == slot else 0 for node in node_order] for slot in range(num_slots)]


def column_labels(node_order: Sequence[str]) -> tuple[list[str], str]:
    """Shorten headers by dropping a shared alphabetic prefix (``Node_01`` -> ``01``).

    Returns (labels, removed_prefix). Falls back to full IDs whenever stripping
    would make a label empty or ambiguous, so every node stays identifiable.
    """
    if len(node_order) < 2:
        return list(node_order), ""
    prefix = os.path.commonprefix(list(node_order)).rstrip("0123456789")
    labels = [node[len(prefix):] for node in node_order]
    if not prefix or any(not label for label in labels) or len(set(labels)) != len(labels):
        return list(node_order), ""
    return labels, prefix


def render_mapping(assignment: Mapping[str, int], node_order: Sequence[str]) -> str:
    width = max((len(n) for n in node_order), default=0)
    return "\n".join(f"  {node:<{width}} : Slot {assignment[node]}" for node in node_order)


def render_matrix(assignment: Mapping[str, int], node_order: Sequence[str]) -> str:
    labels, prefix = column_labels(node_order)
    matrix = build_slot_matrix(assignment, node_order)
    widths = [max(len(label), 1) for label in labels]
    row_head = "Slot \\ Node"

    header = f"{row_head} | " + " | ".join(label.center(w) for label, w in zip(labels, widths))
    rule = "-" * len(header)
    rows = [
        f"{f'Slot {slot:02d}':<{len(row_head)}} | "
        + " | ".join(str(cell).center(w) for cell, w in zip(row, widths))
        for slot, row in enumerate(matrix)
    ]
    note = [f"(column headers omit the common prefix '{prefix}')"] if prefix else []
    return "\n".join([*note, header, rule, *rows, rule])


def _kv(label: str, value: object) -> str:
    return f"{label:<38}: {value}"


def render_report(plan: SchedulePlan, slot_duration_ms: float = DEFAULT_SLOT_MS) -> str:
    """Full report. Only called after the pipeline has validated the schedule."""
    g, cfg, exact = plan.communication_graph, plan.config, plan.exact
    n, k = g.number_of_nodes(), plan.num_slots
    degrees = dict(g.degree)
    max_deg_node = max(plan.node_order, key=lambda v: degrees[v]) if n else None
    isolated = [v for v in plan.node_order if degrees[v] == 0]
    slot_sizes = [sum(1 for s in plan.assignment.values() if s == slot) for slot in range(k)]

    lines = [
        "=" * WIDTH,
        "TDMA TOPOLOGY OPTIMIZATION REPORT".center(WIDTH),
        "=" * WIDTH,
        _kv("Total Nodes Processed", n),
        _kv("Configured Radio Range", f"{cfg.radio_range:.1f} meters"),
        _kv("Optimized Frame Length", f"{k} unique timeslots (lower is better)"),
        _kv("Lower Bound (largest conflict clique)", exact.lower_bound),
        _kv("Optimality", exact.optimality.value),
        "-" * WIDTH,
        "TOPOLOGY (communication graph G)",
        _kv("  Radio links (<= range)", g.number_of_edges()),
        _kv("  Connected components", len(plan.components)),
        _kv("  Max degree", f"{degrees[max_deg_node]} ({max_deg_node})" if n else 0),
        _kv("  Isolated radios", ", ".join(isolated) if isolated else "none"),
        "",
        "CONFLICTS (conflict graph H = G^2)",
        _kv("  Conflicting pairs", plan.conflicts.total),
        _kv("    1-hop  direct link", plan.conflicts.one_hop),
        _kv("    2-hop  hidden terminal", plan.conflicts.two_hop),
        _kv("  Largest clique (all need own slot)", ", ".join(exact.clique_witness) or "-"),
        "",
        "OPTIMIZATION (slots per heuristic)",
        f"  {'Heuristic':<44}{'Runs':>5}{'Best':>6}{'Worst':>7}{'Mean':>7}",
    ]
    for attempt in plan.heuristic.attempts:
        name = attempt.method + (" [DSATUR baseline]" if attempt.method == BASELINE_STRATEGY else "")
        lines.append(
            f"  {name:<44}{attempt.runs:>5}{attempt.best:>6}{attempt.worst:>7}{attempt.mean:>7.2f}"
        )
    search = (
        f"{exact.search_nodes} search nodes" if exact.search_nodes
        else "not needed (lower bound already met)" if exact.num_slots <= exact.lower_bound
        else "disabled or skipped"
    )
    lines += [
        _kv("  Selected method", plan.method),
        _kv("  Exact branch-and-bound", search),
        "",
        "FRAME",
        _kv("  Slot duration", f"{slot_duration_ms:g} ms"),
        _kv("  Frame duration", f"{k * slot_duration_ms:g} ms ({k} slots)"),
        _kv("  Spatial reuse factor (nodes/slots)", f"{n / k:.2f}" if k else "-"),
        _kv("  Slots shared by 2+ radios", f"{sum(1 for s in slot_sizes if s > 1)} of {k}"),
        "-" * WIDTH,
        "NODE -> SLOT ASSIGNMENTS:",
        render_mapping(plan.assignment, plan.node_order),
        "",
        "STRUCTURAL TDMA SCHEDULE MATRIX (Slot x Node Boolean Matrix):",
        render_matrix(plan.assignment, plan.node_order),
        f"Execution finalized cleanly. Schedule verified conflict-free "
        f"({plan.validation.pairs_checked} one/two-hop pairs checked independently).",
        "=" * WIDTH,
    ]
    return "\n".join(lines)
