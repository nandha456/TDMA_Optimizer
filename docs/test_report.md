# Test Report

## Environment (where these results were produced)

| Item | Value |
|---|---|
| OS | Linux 6.18 x86_64 (glibc 2.39) |
| Python | 3.13.16 |
| NetworkX | 3.6.1 |
| Runner | `python -m unittest discover -s tests -t .` |
| Date | 2026-10-09 (Part 1), 2026-10-14 (Part 2) |

**About pytest.** The suite is written as `unittest.TestCase` classes, which pytest collects without changes. The build environment had no access to PyPI, so pytest could not be installed and the suite was executed with the standard-library runner. `python -m pytest` has **not** been run in this environment. On a machine with internet access, run `pip install -e ".[dev]" && python -m pytest`, which should collect the same 102 tests.

## Result

```
Ran 102 tests in 1.218s

OK
```

All 102 tests passed. No test was skipped, weakened or marked as an expected failure.

| File | Tests | Covers |
|---|---|---|
| `test_input_parser.py` | 19 | valid JSON, malformed JSON, non-object, empty, duplicate IDs, empty or whitespace IDs, wrong dimension, null or dict coordinates, strings, booleans, NaN, ±Infinity, 1e999 overflow, missing file, node count with hint, natural ordering |
| `test_topology.py` | 9 | exactly 500 m → edge, 500.001 m → no edge, horizontal, vertical and diagonal (3-4-5) distances, configurable range, node attributes, no self-loops, duplicate coordinates, no-edge input, invalid ranges, components |
| `test_conflict_graph.py` | 10 | direct link, 2-hop hidden terminal, 3-hop not a conflict, disconnected components, no-edge input, attribute preservation, **`nx.power` equals independent BFS on 25 random topologies**, grid statistics (90 = 42 + 48), coloring G alone is insufficient, purity |
| `test_coloring.py` | 14 | valid nontrivial coloring, contiguous slots, same-seed reproducibility, never worse than any attempt, selection without refinement, all strategies attempted, chain spatial reuse (A and D share a slot), component reuse, no-edge case = 1 slot, zero restarts, argument checks, normalization preserves conflicts, iterated greedy never increases K |
| `test_exact.py` | 10 | grid clique = 9, clique ≥ Δ+1, empty graph, proof by clique, **ring_7 proven by search**, search improves a 16-slot incumbent to 9, search opens slots beyond the clique, even cycle, budget exhaustion → "heuristic", budget 0 disables |
| `test_validator.py` | 7 | valid accepted, 1-hop and 2-hop rejection with the named pair, missing and unknown nodes, bad slot types, 3-hop ignored, **the PDF's sample output is rejected on the PDF grid** |
| `test_report.py` | 7 | one `1` per node column, matrix ⇔ mapping, rows ordered, each node once in the header, *printed* text parsed back and cross-checked, report fields, label prefix safety |
| `test_emane_export.py` | 5 | XML structure, each NEM in exactly its slot, NEM numbering, custom parameters, input checks |
| `test_emane_scenario.py` | 8 | valid schedule predicts every link delivered, hidden terminal predicts a collision at the middle node, same-slot neighbours predict "receiver transmitting", prediction agrees with the validator, the G-only control is proper on G but not on G² (64 predicted losses on the grid), complete scenario files (16 platforms, ports, slot duration), CLI writes both scenarios, bad input exits 2 |
| `test_cli.py` | 13 | 16-node file run, inline JSON (4 nodes), wrong count → exit 2, invalid JSON → exit 2 with clean stdout, mutually exclusive inputs, input required, bad range, no-edge topology, same seed gives identical output, EMANE XML export, `python -m tdma_optimizer` subprocess, 40 random 16-node end-to-end runs, **validation gate catches an injected optimizer bug** |

### Mandatory checklist (specification §8)

| # | Requirement | Test(s) |
|---|---|---|
| 1 | Valid JSON input | `test_parses_valid_json`, `test_loads_example_file` |
| 2 | Invalid JSON input | `test_malformed_json`, `test_invalid_json_fails_cleanly` |
| 3 | Malformed and non-finite coordinates | `test_wrong_dimension`, `test_string_coordinates`, `test_boolean_coordinates`, `test_non_finite` |
| 4 | Incorrect node count | `test_incorrect_count_rejected_with_hint`, `test_wrong_node_count_fails` |
| 5 | Exactly 500 m → edge | `test_exactly_500m_creates_edge` |
| 6 | > 500 m → no edge | `test_beyond_500m_no_edge` |
| 7 | Horizontal, vertical, diagonal distance | `test_horizontal_vertical_diagonal_distances` |
| 8 | Direct-link interference | `test_direct_link_is_conflict`, `test_direct_link_conflict_rejected` |
| 9 | Two-hop interference | `test_two_hop_hidden_terminal_is_conflict`, `test_hidden_terminal_conflict_rejected` |
| 10 | Three hops apart not in conflict | `test_three_hops_apart_not_in_conflict`, `test_pairs_within_two_hops_ignores_three_hops` |
| 11 | Disconnected components | `test_disconnected_components_reported`, `test_disconnected_components_never_conflict`, `test_disconnected_components_reuse_slots` |
| 12 | Duplicate coordinates | `test_duplicate_coordinates_are_linked` |
| 13 | Valid coloring, nontrivial graph | `test_valid_coloring_for_nontrivial_graph`, `test_random_16_node_topologies_are_valid` |
| 14 | Invalid coloring rejected | `test_validator.py` (all rejection tests) |
| 15 | Each node exactly once in the matrix | `test_every_node_has_exactly_one_transmit_slot`, `test_rows_are_numeric_slots_and_nodes_in_header_once` |
| 16 | Same seed is reproducible | `test_same_seed_is_reproducible`, `test_same_seed_same_output` |
| 17 | 16-node end-to-end | `test_16_node_file_input`, `test_random_16_node_topologies_are_valid` |
| 18 | No communication edges | `test_no_edges_when_all_far_apart`, `test_no_edges_needs_one_slot`, `test_no_edges_topology` |

Tests assert *properties* (validity, slot count against a proven bound, matrix-mapping agreement) rather than one exact coloring, except where the optimum is unique up to relabeling.

## Part 2: EMANE experiment (measured)

`emane/run_demo.sh` ran on the same VM (2 vCPU) with EMANE 1.5.2 in Docker, real-time scheduling on, 20 s of traffic per run.

| Check | Result |
| --- | --- |
| Link-level predictions matched (2 ms and 4 ms slots, both schedules, both topologies) | **396/396** |
| Collision drops, optimized schedule (all 5 runs incl. 1 ms) | **0** |
| Collision drops, G-only control, grid at 4 ms | 12,629 frames |
| Frames received between out-of-range radios (all 10 runs) | 0 |
| Optimized grid delivery at 1 / 2 / 4 ms slots | 79.7% / 98.7% / 99.7% (losses are late frames, not collisions) |

Full tables: `docs/emane_integration.md` §6.

## Mutation check: do the tests catch real bugs?

Bugs were injected into the source one at a time, the suite was re-run, and the change was reverted (`git checkout`).

| # | Injected bug | Result |
|---|---|---|
| M1 | Range boundary made exclusive (`<` instead of `<=`) | caught (3 tests) |
| M2 | Conflict graph = G instead of G² | caught (91 tests) |
| M3 | Validator ignores 2-hop pairs | caught (28 tests) |
| M4 | Optimizer keeps the *worst* coloring | initially **survived**, now caught (see below) |
| M5 | Branch-and-bound can never open a new slot | initially **survived**, now caught |
| M6 | Parser accepts booleans as numbers | caught |
| M7 | Matrix bits inverted | caught (4 tests) |
| M8 | Iterated greedy accepts worse recolorings | survives; performance-only (see below) |
| M9 | Branch-and-bound without clique pre-coloring | survives; performance-only |

M4 and M5 were real test gaps. Downstream stages repaired M4's damage, and no test needed the search to go above the clique size for M5. Two tests were added: `test_selection_alone_picks_minimum_attempt` and `test_search_opens_slots_beyond_the_clique`. Both mutants are now caught.

M8 and M9 cannot change the output. The refined coloring is only adopted if it is strictly better, and symmetry breaking only prunes search. They affect speed, not correctness.

## Representative topology results (`tdma-optimizer` CLI, exit status 0 for all)

| Input | Nodes | Links | Conflict pairs (1-hop / 2-hop) | Components | Slots | Lower bound | Status |
|---|---|---|---|---|---|---|---|
| `grid_16.json` | 16 | 42 | 90 (42 / 48) | 1 | 9 | 9 | proven (clique) |
| `field_16.json` | 16 | 15 | 30 (15 / 15) | 2 | 4 | 4 | proven (clique) |
| `ring_7.json` | 7 | 7 | 14 (7 / 7) | 1 | 4 | 3 | proven (branch-and-bound, 4 search nodes) |
| `spec_4.json` | 4 | 5 | 6 (5 / 1) | 1 | 4 | 4 | proven (clique) |

Unedited outputs are in `docs/sample_output/`. The heuristic comparison across 290 random deployments is in `docs/algorithm_design.md` §6, produced by `scripts/benchmark.py`.

## Verified CLI behaviors

| Command | Exit |
|---|---|
| `tdma-optimizer --input examples/grid_16.json --range 500 --expected-nodes 16 --seed 42 --restarts 100` | 0 |
| `tdma-optimizer --coordinates '<4-node JSON>' --expected-nodes 4` | 0 |
| `python -m tdma_optimizer --input examples/field_16.json` | 0 |
| `--expected-nodes 4` with a 16-node file | 2 |
| `--coordinates '{bad'` | 2 |
| `--input` together with `--coordinates` | 2 |
| `--range -5` | 2 |

## Known limitations of this testing

- The suite was run with `unittest`, not pytest (see above).
- Random-topology tests use the uniform-square model only. Clustered or line-like deployments are covered by the hand-built examples.
- EMANE runs are an experiment, not part of the unit suite: they need Docker and privileged containers. Their results are in `docs/emane_integration.md` §6 and `emane/results/`.
- Package installation was tested as an editable install with `--no-build-isolation`, because the environment was offline. A normal `pip install -e .` downloads setuptools for the isolated build.
