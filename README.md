# TDMA Schedule Optimizer

A centralized "network brain" that assigns collision-free TDMA time slots to a multi-hop wireless network using **distance-2 graph coloring**, minimizes the frame length with a portfolio of heuristics, and **proves** when the result is optimal.

Built for the Vaan Megam Networks Wireless Protocol Development assessment (Part 1, mandatory), with a tested EMANE schedule exporter and integration plan for Part 2.

## Headline results

| Topology | Radios | Slots | Lower bound | Status |
|---|---|---|---|---|
| `grid_16`: 4×4 grid, 300 m spacing (the PDF example coordinates) | 16 | **9** | 9 | Proven optimal (clique bound) |
| `field_16`: convoy plus separate outpost, 2 components | 16 | **4** | 4 | Proven optimal (clique bound), 4× spatial reuse |
| `ring_7`: 7 radios on a ring | 7 | **4** | 3 | Proven optimal (exhaustive branch-and-bound) |
| 200 random 16-node deployments (1.5 km square) | 16 | mean 7.67 | n/a | 200/200 proven optimal |

> **Why 9 slots and not the 5 in the PDF's sample output?** In the 4×4 / 300 m grid, `Node_06` has 8 neighbors (orthogonal at 300 m, diagonal at 424 m). It and those neighbors are all within two hops of each other, so those 9 radios form a clique in the conflict graph. Each needs its own slot, so **no valid schedule can use fewer than 9 slots.** The PDF's sample gives `Node_01` and `Node_03` the same slot even though both are neighbors of `Node_02`. That is exactly the hidden-terminal collision the task forbids. `tests/test_validator.py::test_pdf_sample_output_is_not_valid_for_the_pdf_grid` demonstrates this. The sample is best read as a format illustration.

## The problem in one picture

```
Direct link (1 hop)        Hidden terminal (2 hops)          Spatial reuse (3+ hops)
  A ----- B                  A ----- B ----- C                A -- B -- C -- D
  slot(A) != slot(B)         slot(A) != slot(C)               slot(A) == slot(D) allowed
                             (A and C collide at B)
```

Two radios conflict iff their hop distance in the communication graph G is 1 or 2, which is exactly an edge in **G²**. Minimizing slots therefore means minimizing the colors of G² (NP-hard in general).

## Pipeline

```
JSON coordinates
  -> input_parser   strict validation (NaN, bools, duplicates, dimensions ...)
  -> topology       G: edge iff euclidean distance <= range (inclusive)
  -> conflict_graph H = G^2, edges tagged 1-hop / 2-hop
  -> coloring       DSATUR baseline + 5 greedy orders + seeded random restarts
                    + iterated-greedy refinement -> best valid coloring
  -> exact          clique lower bound; bounded branch-and-bound if a gap remains
  -> validator      independent BFS re-check from G (does not trust H)  [gate]
  -> report         stats, node->slot mapping, Slot x Node boolean matrix
  -> emane_export   optional EMANE TDMA schedule XML (Part 2 bridge)
```

## Project layout

```
tdma-optimizer/
├── pyproject.toml
├── README.md
├── examples/                 grid_16, field_16, ring_7, spec_4 (+ a generated EMANE XML)
├── scripts/benchmark.py      reproducible heuristic comparison
├── src/tdma_optimizer/
│   ├── cli.py                argument parsing and exit codes only
│   ├── pipeline.py           orchestration; the single entry point for all logic
│   ├── input_parser.py       JSON -> validated coordinates
│   ├── topology.py           communication graph G
│   ├── conflict_graph.py     conflict graph H = G^2
│   ├── coloring.py           heuristic portfolio
│   ├── exact.py              lower bound and bounded branch-and-bound certificate
│   ├── validator.py          independent schedule verification
│   ├── report.py             ASCII report and matrix
│   ├── emane_export.py       EMANE schedule XML
│   └── errors.py             exception hierarchy -> exit codes
├── tests/                    94 tests, one file per module plus end-to-end CLI tests
└── docs/
    ├── architecture.md
    ├── algorithm_design.md
    ├── test_report.md
    ├── emane_integration.md
    ├── presentation_guide.md
    └── sample_output/        genuine CLI output, unedited
```

## Install

Requires Python 3.11+ on Linux or macOS.

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Run

```bash
# The 16-node assessment topology from a file
tdma-optimizer --input examples/grid_16.json --range 500 --expected-nodes 16 --seed 42 --restarts 100

# Inline JSON, as in the problem statement (match --expected-nodes to the node count)
tdma-optimizer --coordinates '{"Node_01":[0.0,0.0],"Node_02":[300.0,0.0],"Node_03":[600.0,0.0],"Node_04":[300.0,400.0]}' --expected-nodes 4

# Also write an EMANE TDMA schedule
tdma-optimizer --input examples/grid_16.json --emane-xml schedule.xml

# Without installing the console script
python -m tdma_optimizer --input examples/field_16.json
```

| Option | Default | Meaning |
|---|---|---|
| `--input FILE` / `--coordinates JSON` | required, mutually exclusive | Node coordinates in meters |
| `--range` | 500 | Radio range in meters, inclusive boundary |
| `--expected-nodes` | 16 | Required node count (enforced) |
| `--seed` | 42 | Seed for randomized attempts |
| `--restarts` | 100 | Number of random-order greedy attempts |
| `--exact-budget` | 200000 | Branch-and-bound node budget; `0` disables it |
| `--emane-xml FILE` | off | Write the EMANE schedule XML |
| `-v` | off | Progress logging to stderr |

**Exit codes:** `0` success · `2` usage or input error · `3` schedule failed verification (never printed as success).

## Sample output (genuine, `grid_16`)

```
========================================================================
                   TDMA TOPOLOGY OPTIMIZATION REPORT
========================================================================
Total Nodes Processed                 : 16
Configured Radio Range                : 500.0 meters
Optimized Frame Length                : 9 unique timeslots (lower is better)
Lower Bound (largest conflict clique) : 9
Optimality                            : proven optimal: equals clique lower bound
...
NODE -> SLOT ASSIGNMENTS:
  Node_01 : Slot 0
  Node_02 : Slot 1
  ...
STRUCTURAL TDMA SCHEDULE MATRIX (Slot x Node Boolean Matrix):
(column headers omit the common prefix 'Node_')
Slot \ Node | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 13 | 14 | 15 | 16
-------------------------------------------------------------------------------------------
Slot 00     | 1  | 0  | 0  | 1  | 0  | 0  | 0  | 0  | 0  | 0  | 0  | 0  | 1  | 0  | 0  | 1
Slot 01     | 0  | 1  | 0  | 0  | 0  | 0  | 0  | 0  | 0  | 0  | 0  | 0  | 0  | 1  | 0  | 0
...
Execution finalized cleanly. Schedule verified conflict-free (90 one/two-hop pairs checked independently).
```

The full, unedited reports are in [`docs/sample_output/`](docs/sample_output/).

## Test

```bash
python -m pytest                                 # with the dev extra installed
python -m unittest discover -s tests -t .        # standard library only, same tests
```

The tests are written as `unittest.TestCase` classes, which pytest collects natively. See [docs/test_report.md](docs/test_report.md) for what was executed and how.

## Known limitations

- **Interference model is graph-based.** The model uses a hard range disk and the protocol-model two-hop rule. It does not model SINR, aggregate interference from many distant transmitters, or a carrier-sense range larger than the communication range.
- **Static topology.** One schedule is computed for one snapshot. Mobility would require periodic recomputation and an EMANE update schedule.
- **One transmit slot per node.** Slots are not weighted by traffic demand. A relay carrying more traffic gets the same share as a leaf node.
- **Exact search is bounded.** For large or adversarial graphs it may stop at its budget. The report then says "best found (optimality not proven)".
- **Inclusive boundary is exact.** No floating-point epsilon is used, as specified. Coordinates within about 1e-13 m of the range could fall either side.
- **EMANE output is format-checked, not run.** The XML follows the official TDMA model documentation but has not been loaded into a live EMANE instance here.
