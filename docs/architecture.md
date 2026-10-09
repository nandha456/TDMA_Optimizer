# Architecture

## Design principles

1. **One pipeline, many front-ends.** `pipeline.plan_schedule()` is the only place where the stages are wired together. The CLI, the tests, the benchmark script and the EMANE exporter all call it, so business logic is never duplicated.
2. **Every stage is a pure function over plain data.** Inputs are coordinates or NetworkX graphs; outputs are dicts or frozen dataclasses. No module keeps global mutable state, so each stage can be tested on its own.
3. **Never report what was not verified.** The validator re-derives the constraints independently, and the pipeline raises instead of returning an invalid schedule.
4. **Determinism.** Nodes are inserted in natural order (`Node_2` before `Node_10`), all tie-breaks follow that order, and all randomness comes from one seeded `random.Random`. Same input and seed give byte-identical output.

## Data flow

```
                ┌────────────────┐
 JSON text ───▶ │ input_parser   │──▶ Coordinates  {node: (x, y)}, naturally ordered
                └────────────────┘
                        │  check_node_count (CLI)
                        ▼
                ┌────────────────┐
                │ topology       │──▶ G  (nx.Graph, node attr pos, edge attr distance)
                └────────────────┘
                        ▼
                ┌────────────────┐
                │ conflict_graph │──▶ H = G² (edge attr hops ∈ {1,2}) + ConflictStats
                └────────────────┘
                        ▼
                ┌────────────────┐
                │ coloring       │──▶ HeuristicResult (best valid coloring + per-method stats)
                └────────────────┘
                        ▼
                ┌────────────────┐
                │ exact          │──▶ ExactResult (lower bound, witness clique, optimality,
                └────────────────┘     possibly an improved coloring)
                        ▼
                ┌────────────────┐
                │ validator      │──▶ ValidationResult   ── invalid? raise ScheduleValidationError
                └────────────────┘
                        ▼
                  SchedulePlan  ──▶ report.render_report()      (stdout)
                                ──▶ emane_export.build_schedule_xml()  (optional file)
```

## Module responsibilities

| Module | Responsibility | Depends on |
|---|---|---|
| `errors.py` | `TdmaError` → `InputValidationError`, `ScheduleValidationError` | none |
| `input_parser.py` | Strict JSON parsing, natural ordering, node-count check | errors |
| `topology.py` | Range validation, building G, connected components | input_parser |
| `conflict_graph.py` | H = G², hop tagging, conflict statistics | networkx |
| `coloring.py` | Heuristic portfolio, slot normalization, iterated greedy | networkx |
| `exact.py` | Clique lower bound, bounded DSATUR branch-and-bound | coloring |
| `validator.py` | Independent BFS-based verification | input_parser |
| `pipeline.py` | Orchestration and the validation gate | all of the above |
| `report.py` | ASCII report, mapping, Slot × Node matrix | pipeline |
| `emane_export.py` | Schedule → EMANE TDMA XML, NEM numbering | errors |
| `cli.py` | argparse, exit codes, file output | pipeline, report, emane_export |

The dependency graph has no cycles. `cli.py` is the only module that touches `sys.argv`, stdout, stderr or exit codes.

## Why G and H are separate objects

- **They mean different things.** G answers "who can hear whom" and is what EMANE's radios physically experience. H answers "who must not share a slot" and exists only for scheduling. Keeping G lets the report show real link counts, components and degrees, and lets the validator check against ground truth.
- **They change for different reasons.** A different interference model (for example, a carrier-sense range larger than the communication range, or SINR-based conflicts) changes only how H is built. Topology parsing, coloring and reporting stay the same.
- **Independent verification needs G.** If the validator checked the coloring against H, a bug in building H would go unnoticed. The validator instead runs a depth-2 BFS on G (see below).

## Error propagation

| Failure | Raised in | Type | CLI behavior |
|---|---|---|---|
| Malformed JSON, bad coordinates, duplicate IDs | `input_parser` | `InputValidationError` | message to stderr, exit 2 |
| Wrong node count | `input_parser.check_node_count` | `InputValidationError` | message with hint, exit 2 |
| Range ≤ 0, NaN, ∞ | `topology.validate_range` | `InputValidationError` | exit 2 |
| Bad CLI flags, both or neither input given | argparse | `SystemExit(2)` | usage message, exit 2 |
| Cannot write the EMANE file | `cli` | `OSError`, caught | exit 2 |
| Schedule fails verification | `pipeline` | `ScheduleValidationError` | each violation listed, exit 3 |
| Anything else (a bug) | anywhere | not caught | traceback, non-zero exit |

Only *expected* failure types are caught. Unexpected exceptions are deliberately not swallowed, so a bug can never be mistaken for a clean run.

## How validation gates report generation

```python
validation = validate_schedule(graph, exact.assignment)   # independent of H
if not validation.is_valid:
    raise ScheduleValidationError(..., validation.errors)
return SchedulePlan(...)                                  # only valid plans exist
```

`render_report()` takes a `SchedulePlan`, and a `SchedulePlan` can only be constructed after validation passes. The text "Schedule verified conflict-free" can therefore never appear for an invalid schedule. `tests/test_cli.py::Pipeline::test_validation_gate_is_wired` proves this by injecting a broken optimizer and asserting the pipeline raises.

The validator itself:

1. Every node in G has a slot, and there are no slots for unknown nodes.
2. Every slot is a non-negative `int` (booleans and floats rejected).
3. For every node, `single_source_shortest_path_length(G, v, cutoff=2)` lists all nodes 1 or 2 hops away. Any such pair sharing a slot is a violation, reported with its hop count.

## Extension points

- **Different interference model:** replace `build_conflict_graph`. Everything downstream works on any H.
- **Traffic-weighted slots:** give each node a demand d(v) and color a graph where node v is expanded into d(v) mutually conflicting copies.
- **Another emulator or a real radio:** add an exporter beside `emane_export.py` that consumes `SchedulePlan`.
