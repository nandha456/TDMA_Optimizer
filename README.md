# TDMA Schedule Optimizer

A centralized "network brain" that assigns collision-free TDMA time slots to a multi-hop radio network. It drives a real-time **EMANE** emulation that enforces the schedule on live packets.

Submission for the Vaan Megam Networks Wireless Protocol Development assessment. **Part 1 (Brain): complete. Part 2 (EMANE): implemented and measured.**

📄 **Full documentation:** [`docs/TDMA_Optimizer_Documentation.pdf`](docs/TDMA_Optimizer_Documentation.pdf)

## Results at a glance

| | Result |
|---|---|
| 16-radio assessment grid | **9 slots, proven optimal.** No valid schedule can use fewer: `Node_06` and its 8 neighbours all conflict with each other |
| Spatial reuse | Field layout: 16 radios in **4 slots** (each slot used by 4 radios) |
| Optimality proof | Every schedule is labelled *proven optimal* or *best found*, never guessed. 200/200 random 16-radio networks were proven optimal |
| Collisions in EMANE | **0 collision drops** for the optimized schedule, in every run |
| Prediction vs EMANE | **396/396** directed-link outcomes predicted by the Brain matched EMANE's measured delivery (2 topologies, 2 schedules, 2 ms and 4 ms slots) |
| Control experiment | A schedule that ignores 2-hop conflicts lost 97–99% of frames on exactly the 64 links the Brain predicted |
| Tests | 102 automated tests, all passing |

## Try it (3 commands)

```bash
python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
tdma-optimizer --input examples/grid_16.json        # Part 1: schedule + matrix
emane/run_demo.sh                                   # Part 2: needs Docker, ~5 minutes
```

Inline JSON, as in the problem statement:

```bash
tdma-optimizer --coordinates '{"Node_01":[0.0,0.0],"Node_02":[300.0,0.0],"Node_03":[600.0,0.0],"Node_04":[300.0,400.0]}' --expected-nodes 4
```

## How it works

```
Part 1 (Brain, Python)                                   Part 2 (Engine, EMANE in Docker)
 coordinates (JSON)                                       16 NEMs, TDMA radio model, 1 MHz @ 2.4 GHz
   → G   radio graph: link if distance ≤ 500 m            ▲ schedule.xml       (TDMA schedule event)
   → H = G²  conflicts: 1 hop or 2 hops apart             ▲ pathloss per link  (EMANE "hears" exactly G)
   → color H with as few colors as possible   ──────────▶ ▼ every radio broadcasts frames
     (DSATUR + 5 orderings + 100 seeded random + refine)  ▼ EMANE delivers or drops them per slot
   → prove optimal (clique bound / branch-and-bound)      ▼ measured delivery, per link
   → independent validation → report + EMANE XML  ◀────── compare with the Brain's prediction
```

**The one idea:** two radios may not share a slot if they are neighbours (1 hop), or if they share a neighbour (2 hops: the *hidden terminal*, which collides at the middle radio). Those pairs are exactly the edges of the square graph **G²**, so a collision-free schedule is a proper coloring of G², and each color is a time slot. Radios 3 or more hops apart can reuse a slot (spatial reuse).

### Sample output (`grid_16`)

```
Total Nodes Processed                 : 16
Configured Radio Range                : 500.0 meters
Optimized Frame Length                : 9 unique timeslots (lower is better)
Lower Bound (largest conflict clique) : 9
Optimality                            : proven optimal: equals clique lower bound
...
Slot \ Node | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 13 | 14 | 15 | 16
Slot 00     | 1  | 0  | 0  | 1  | 0  | 0  | 0  | 0  | 0  | 0  | 0  | 0  | 1  | 0  | 0  | 1
Slot 01     | 0  | 1  | 0  | 0  | 0  | 0  | 0  | 0  | 0  | 0  | 0  | 0  | 0  | 1  | 0  | 0
...
Execution finalized cleanly. Schedule verified conflict-free (90 one/two-hop pairs checked independently).
```

Full unedited outputs: [`docs/sample_output/`](docs/sample_output/).

> **About the assessment's 5-slot sample output.** For the assessment's own example coordinates (4×4 grid, 300 m spacing), 500 m range reaches the diagonal neighbours (424 m). So `Node_06` and its 8 neighbours are pairwise within 2 hops and need 9 different slots: **9 is a proven minimum.** The sample also gives `Node_01` and `Node_03` the same slot while both neighbour `Node_02`, a hidden-terminal collision. `tests/test_validator.py` checks this, and the EMANE control run shows such a schedule losing packets.

## Repository map

```
src/tdma_optimizer/
  input_parser.py     JSON → validated coordinates
  topology.py         communication graph G
  conflict_graph.py   conflict graph H = G²
  coloring.py         heuristic portfolio (DSATUR baseline)
  exact.py            lower bound + bounded branch-and-bound (optimality proof)
  validator.py        independent schedule check (does not trust H)
  pipeline.py         runs the stages; refuses to return an invalid schedule
  report.py           ASCII report, node→slot mapping, Slot × Node matrix
  cli.py              tdma-optimizer command
  emane_export.py     schedule → EMANE TDMA schedule XML
  emane_scenario.py   tdma-emane-scenario: full EMANE scenario + per-link prediction
emane/
  run_demo.sh         Part 2 in one command
  run_experiment.py   runs inside the EMANE container
  analyze.py          prediction vs measurement
  Dockerfile          EMANE 1.5.2 from official source
  results/            measured results (grid_16, field_16)
tests/                102 tests, one file per module
examples/             grid_16, field_16, ring_7, spec_4
scripts/benchmark.py  heuristic comparison on random networks
docs/                 documentation PDF and detailed design notes
```

## Documentation

| Document | Contents |
|---|---|
| [`docs/TDMA_Optimizer_Documentation.pdf`](docs/TDMA_Optimizer_Documentation.pdf) | **Main submission document:** design process, reasoning, Part 1 and Part 2, final values |
| [`docs/algorithm_design.md`](docs/algorithm_design.md) | The math: G², greedy coloring, DSATUR, lower bounds, complexity, benchmark |
| [`docs/architecture.md`](docs/architecture.md) | Modules, data flow, error handling, validation gate |
| [`docs/emane_integration.md`](docs/emane_integration.md) | Part 2: configuration, experiment, measured results, how to reproduce |
| [`docs/test_report.md`](docs/test_report.md) | What was tested and how; mutation check |

## CLI reference

| Option | Default | Meaning |
|---|---|---|
| `--input FILE` / `--coordinates JSON` | one required | Node coordinates in meters |
| `--range` | 500 | Radio range in meters, inclusive |
| `--expected-nodes` | 16 | Required node count (enforced) |
| `--seed` / `--restarts` | 42 / 100 | Reproducible randomized attempts |
| `--exact-budget` | 200000 | Branch-and-bound budget (0 disables) |
| `--emane-xml FILE` | off | Also write the EMANE schedule XML |

Exit codes: `0` success · `2` input error · `3` schedule failed verification (never printed as success).

## Testing

```bash
python -m pytest                                # or: python -m unittest discover -s tests -t .
python scripts/benchmark.py                     # heuristic comparison, 200 random networks
```

## Known limitations

- **Graph interference model:** hard 500 m disk, 2-hop rule. It does not model SINR from many distant transmitters, or a carrier-sense range larger than the communication range.
- **Static topology, one slot per radio.** Mobility and traffic-weighted slots are natural extensions (see the documentation).
- **1 ms slots in EMANE need CPU headroom.** On a 2-vCPU VM, 16 emulated radios at 1 ms produced late-frame drops (never collisions). At 2 ms and 4 ms, delivery was 98.7% and 99.7%.
- The optimality search is bounded. If it hits its budget, the report says "best found (optimality not proven)".
