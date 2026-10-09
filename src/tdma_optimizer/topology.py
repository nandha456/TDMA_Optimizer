"""Build the communication graph G from radio coordinates.

An undirected edge (u, v) exists iff ``euclidean_distance(u, v) <= radio_range``.
The boundary is inclusive and compared exactly (no epsilon), as specified.
"""

from __future__ import annotations

import itertools
import math

import networkx as nx

from tdma_optimizer.errors import InputValidationError
from tdma_optimizer.input_parser import Coordinates, natural_key

DEFAULT_RANGE_M = 500.0


def validate_range(radio_range: float) -> float:
    """Return the range as float, rejecting zero, negative, NaN or infinite values."""
    if isinstance(radio_range, bool) or not isinstance(radio_range, (int, float)):
        raise InputValidationError(f"Radio range must be a number, got {radio_range!r}.")
    value = float(radio_range)
    if not math.isfinite(value) or value <= 0:
        raise InputValidationError(f"Radio range must be a positive finite number, got {value}.")
    return value


def build_communication_graph(
    coordinates: Coordinates, radio_range: float = DEFAULT_RANGE_M
) -> nx.Graph:
    """Create G: one node per radio, one edge per pair within radio range.

    Node attribute ``pos`` holds ``(x, y)``; edge attribute ``distance`` holds the
    measured Euclidean distance in meters. All O(n^2) pairs are evaluated with
    :func:`math.dist`. Co-located radios (distance 0) are linked, because two
    radios at the same spot certainly interfere. Self-loops cannot arise because
    only distinct pairs are compared.
    """
    limit = validate_range(radio_range)
    graph = nx.Graph(radio_range=limit)
    for node_id in sorted(coordinates, key=natural_key):
        graph.add_node(node_id, pos=coordinates[node_id])

    for u, v in itertools.combinations(graph.nodes, 2):
        distance = math.dist(coordinates[u], coordinates[v])
        if distance <= limit:
            graph.add_edge(u, v, distance=distance)
    return graph


def connected_components(graph: nx.Graph) -> list[list[str]]:
    """Connected components, each naturally sorted, ordered by their first node."""
    components = [sorted(c, key=natural_key) for c in nx.connected_components(graph)]
    return sorted(components, key=lambda c: natural_key(c[0]))
