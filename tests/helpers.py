"""Shared fixtures for the test suite (plain functions so unittest and pytest both work)."""

from __future__ import annotations

import json
import random
from pathlib import Path

import networkx as nx

from tdma_optimizer.conflict_graph import build_conflict_graph
from tdma_optimizer.topology import build_communication_graph

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def grid_16() -> dict[str, tuple[float, float]]:
    """4 x 4 grid, 300 m spacing: the topology implied by the assessment PDF."""
    return {f"Node_{i + 1:02d}": (float(i % 4 * 300), float(i // 4 * 300)) for i in range(16)}


def line(n: int, spacing: float = 400.0) -> dict[str, tuple[float, float]]:
    """Chain A -- B -- C ... with only consecutive nodes in range (for spacing in (250, 500])."""
    return {chr(ord("A") + i): (i * spacing, 0.0) for i in range(n)}


def graphs_for(coords: dict) -> tuple[nx.Graph, nx.Graph]:
    g = build_communication_graph(coords, 500.0)
    return g, build_conflict_graph(g)


def random_coords(seed: int, n: int = 16, side: float = 1500.0) -> dict[str, tuple[float, float]]:
    rng = random.Random(seed)
    return {f"Node_{i + 1:02d}": (rng.uniform(0, side), rng.uniform(0, side)) for i in range(n)}


def as_json(coords: dict) -> str:
    return json.dumps({k: list(v) for k, v in coords.items()})
