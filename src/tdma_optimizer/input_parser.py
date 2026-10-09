"""Parse and validate radio coordinates supplied as JSON.

Expected shape::

    {"Node_01": [0.0, 0.0], "Node_02": [300.0, 0.0], ...}

The parser is strict on purpose: a scheduler that silently accepts a typo'd
coordinate produces a schedule for a network that does not exist.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from tdma_optimizer.errors import InputValidationError

Coordinates = dict[str, tuple[float, float]]

_DIGIT_RUNS = re.compile(r"(\d+)")


def natural_key(node_id: str) -> tuple[Any, ...]:
    """Sort key that orders ``Node_2`` before ``Node_10``.

    Used everywhere a deterministic node order is needed (graph insertion,
    report columns, EMANE NEM numbering) so the whole pipeline agrees on one order.
    """
    parts = _DIGIT_RUNS.split(node_id)
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in parts)


def _reject_constant(name: str) -> float:
    # json.loads accepts the non-standard literals NaN / Infinity / -Infinity by default.
    raise InputValidationError(
        f"Non-finite number '{name}' is not a valid coordinate; use finite meters."
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    # json.loads would otherwise keep the last duplicate and silently drop a radio.
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise InputValidationError(f"Duplicate node identifier '{key}' in input.")
        seen[key] = value
    return seen


def _parse_point(node_id: str, value: Any) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)):
        raise InputValidationError(
            f"{node_id}: coordinates must be a list [x, y], got {type(value).__name__}."
        )
    if len(value) != 2:
        raise InputValidationError(
            f"{node_id}: expected exactly 2 coordinates [x, y], got {len(value)}."
        )
    point: list[float] = []
    for axis, component in zip("xy", value):
        # bool is a subclass of int in Python, so it must be excluded explicitly.
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            raise InputValidationError(
                f"{node_id}: {axis} must be a number, got {component!r}."
            )
        number = float(component)
        if not math.isfinite(number):
            raise InputValidationError(f"{node_id}: {axis} must be finite, got {component!r}.")
        point.append(number)
    return point[0], point[1]


def parse_coordinates(text: str) -> Coordinates:
    """Parse a JSON string into ``{node_id: (x, y)}``, ordered naturally by node ID.

    Raises:
        InputValidationError: on malformed JSON, wrong types, duplicate or empty
            node IDs, wrong coordinate dimensions, booleans, NaN or infinity.
    """
    if not isinstance(text, str):
        raise InputValidationError("Coordinate input must be a JSON string.")
    try:
        raw = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise InputValidationError(
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}."
        ) from exc

    if not isinstance(raw, dict):
        raise InputValidationError(
            'Top-level JSON must be an object like {"Node_01": [0.0, 0.0]}, '
            f"got {type(raw).__name__}."
        )
    if not raw:
        raise InputValidationError("Input contains no nodes.")

    coordinates: Coordinates = {}
    for node_id in sorted(raw, key=natural_key):
        if not node_id.strip():
            raise InputValidationError("Node identifiers must be non-empty strings.")
        if node_id != node_id.strip():
            raise InputValidationError(
                f"Node identifier {node_id!r} has leading or trailing whitespace."
            )
        coordinates[node_id] = _parse_point(node_id, raw[node_id])
    return coordinates


def load_coordinates_file(path: str | Path) -> Coordinates:
    """Read and parse a JSON coordinate file."""
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise InputValidationError(f"Input file not found: {file_path}") from exc
    except OSError as exc:
        raise InputValidationError(f"Cannot read input file {file_path}: {exc}") from exc
    return parse_coordinates(text)


def check_node_count(coordinates: Coordinates, expected: int) -> None:
    """Enforce the configured node count (16 for the assessment topology)."""
    if len(coordinates) != expected:
        raise InputValidationError(
            f"Expected {expected} nodes but received {len(coordinates)}. "
            f"Pass --expected-nodes {len(coordinates)} if this topology is intentional."
        )
