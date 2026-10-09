"""End-to-end planning pipeline, independent of any CLI or output format.

    coordinates -> G -> H = G^2 -> heuristics -> certificate -> validation

The CLI, tests, the benchmark script and the EMANE exporter all call
:func:`plan_schedule`, so the business logic exists in exactly one place.
Validation is a gate: an invalid schedule raises instead of being returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from tdma_optimizer.coloring import (
    DEFAULT_REFINE_PASSES,
    DEFAULT_RESTARTS,
    DEFAULT_SEED,
    Coloring,
    HeuristicResult,
    optimize_schedule,
)
from tdma_optimizer.conflict_graph import ConflictStats, build_conflict_graph, conflict_stats
from tdma_optimizer.errors import ScheduleValidationError
from tdma_optimizer.exact import DEFAULT_NODE_BUDGET, ExactResult, certify
from tdma_optimizer.input_parser import Coordinates
from tdma_optimizer.topology import DEFAULT_RANGE_M, build_communication_graph, connected_components
from tdma_optimizer.validator import ValidationResult, validate_schedule


@dataclass(frozen=True)
class PlanConfig:
    radio_range: float = DEFAULT_RANGE_M
    seed: int = DEFAULT_SEED
    restarts: int = DEFAULT_RESTARTS
    refine_passes: int = DEFAULT_REFINE_PASSES
    exact_budget: int = DEFAULT_NODE_BUDGET


@dataclass(frozen=True)
class SchedulePlan:
    """Everything the report and exporters need, produced by one pipeline run."""

    config: PlanConfig
    communication_graph: nx.Graph = field(repr=False)
    conflict_graph: nx.Graph = field(repr=False)
    components: list[list[str]]
    conflicts: ConflictStats
    heuristic: HeuristicResult
    exact: ExactResult
    assignment: Coloring
    num_slots: int
    method: str
    validation: ValidationResult

    @property
    def node_order(self) -> list[str]:
        return list(self.communication_graph.nodes)


def plan_schedule(coordinates: Coordinates, config: PlanConfig = PlanConfig()) -> SchedulePlan:
    """Compute and verify a collision-free TDMA schedule.

    Raises:
        InputValidationError: invalid range.
        ScheduleValidationError: the final schedule failed independent validation.
    """
    graph = build_communication_graph(coordinates, config.radio_range)
    conflict = build_conflict_graph(graph)

    heuristic = optimize_schedule(
        conflict,
        seed=config.seed,
        restarts=config.restarts,
        refine_passes=config.refine_passes,
    )
    exact = certify(conflict, heuristic.assignment, config.exact_budget)
    method = "branch_and_bound" if exact.improved else heuristic.method

    validation = validate_schedule(graph, exact.assignment)
    if not validation.is_valid:
        raise ScheduleValidationError(
            "Computed schedule failed independent validation; refusing to report it.",
            validation.errors,
        )

    return SchedulePlan(
        config=config,
        communication_graph=graph,
        conflict_graph=conflict,
        components=connected_components(graph),
        conflicts=conflict_stats(conflict),
        heuristic=heuristic,
        exact=exact,
        assignment=exact.assignment,
        num_slots=exact.num_slots,
        method=method,
        validation=validation,
    )
