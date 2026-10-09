# Algorithm Design

## 1. Communication graph G

Each radio i has a position p_i = (x_i, y_i) in meters. For every distinct pair:

    d(u, v) = sqrt((x_u − x_v)² + (y_u − y_v)²)        (math.dist)
    edge (u, v) ∈ G  ⇔  d(u, v) ≤ R                    (R = 500 m, inclusive)

All n(n−1)/2 pairs are evaluated, which is O(n²). This is trivial for 16 nodes and fine into the low thousands; beyond that a spatial grid index would make it near-linear. The measured distance is stored on each edge. Co-located radios (d = 0) are linked, because they certainly interfere. Self-loops cannot occur because only distinct pairs are compared. The comparison is exact (no epsilon), as the specification asks: 3-4-5 geometry such as (0,0)–(300,400) yields exactly 500.0 and is linked.

## 2. Interference model

In TDMA a collision happens at a **receiver**: if two transmissions reach the same radio in the same slot, that radio decodes neither.

- **1 hop (direct link).** If u and v are neighbors, u transmitting while v transmits means v is not listening, and each disrupts the other's receivers. So slot(u) ≠ slot(v).
- **2 hops (hidden terminal).** If u and w share a neighbor v but cannot hear each other, neither can detect the other's transmission. If they use the same slot, their signals overlap at v. So slot(u) ≠ slot(w).
- **3+ hops (spatial reuse).** If u and w are at least 3 hops apart, they have no common neighbor, so no radio can hear both. They may share a slot.

## 3. Why the square graph is exactly the constraint set

The square of G, written G², has the same nodes, with an edge between u and v iff their hop distance in G is 1 or 2. That is precisely the set of pairs that must not share a slot. Therefore:

> A valid TDMA schedule = a proper vertex coloring of H = G².
> Minimum frame length = the chromatic number χ(G²).

Coloring G alone is **insufficient**. In A – B – C, a proper coloring of G may assign A = C (they are not adjacent in G), which is the hidden-terminal collision at B. `tests/test_conflict_graph.py::test_coloring_g_alone_is_insufficient` shows NetworkX doing exactly that on G and avoiding it on G².

H is built with `nx.power(G, 2)`. Each edge is tagged `hops = 1` if it is also in G, otherwise `hops = 2`. As a cross-check, a test compares `nx.power` against an independent BFS on 25 random topologies.

### Worked example: A – B – C – D

```
G :  A ── B ── C ── D           hop distances:  A–B 1, A–C 2, A–D 3
H :  A–B, B–C, C–D   (1-hop)
     A–C, B–D        (2-hop)    A–D is NOT an edge of H
```

- **A and C may not share a slot.** They both neighbor B. If they transmit together, B receives a collision.
- **A and D may share a slot.** A's transmission reaches only B. D's reaches only C. No radio hears both, so no collision is possible.

H here is a triangle A–B–C plus a triangle B–C–D, so it needs 3 slots: A = 0, B = 1, C = 2, D = 0. That is 4 radios in 3 slots, a direct example of spatial reuse (`test_spatial_reuse_on_chain`).

## 4. Heuristic slot minimization

**Objective:** minimize K = |{slot(v)}| subject to slot(u) ≠ slot(v) for every (u, v) ∈ H.

### Greedy coloring

Visit nodes in some order and give each the smallest slot not used by an already-colored conflicting node. The result is always valid. Its quality depends entirely on the order, and some order always achieves χ(H). The task is to find a good order cheaply.

### The portfolio

| Strategy | Order rule | Rationale |
|---|---|---|
| `saturation_largest_first` (**DSATUR**, baseline) | Next node = the one with the most distinct colors among its neighbors; ties go to higher degree | Colors the most constrained node first. Exact on bipartite graphs, strong in practice |
| `largest_first` | Decreasing degree | Places hubs early |
| `smallest_last` | Repeatedly remove the min-degree node, then color in reverse | Uses at most degeneracy + 1 colors; good on sparse or geometric graphs |
| `independent_set` | Repeatedly extract a large independent set as one color | Different structure, adds diversity |
| `connected_sequential_bfs` / `_dfs` | Graph traversal order | Each node has a colored neighbor when visited |
| `random_order` × restarts | Seeded random permutations | Escapes the systematic blind spots of fixed rules |
| Iterated greedy (Culberson) | Recolor with each color class kept contiguous; class order reversed, by size, or shuffled | **Never increases K**, often decreases it |

Why the iterated-greedy guarantee holds: when nodes are revisited class by class, each old color class is an independent set. Every node in the j-th class revisited can always take a color ≤ j, so the total never grows.

**Selection:** every candidate is checked to be a proper coloring of H, and the fewest slots wins. Ties keep the earliest attempt, so DSATUR is selected unless something strictly beats it. More heuristics never make the answer worse, but they are not assumed to make it better. The benchmark measures this.

**Normalization:** slots are relabeled 0..K−1 by first appearance in node order. Relabeling is a bijection on colors, so every pair that differed still differs.

## 5. Proving optimality: lower bound and bounded exact search

Minimum graph coloring is NP-hard (deciding whether χ ≤ 3 is NP-complete, and χ is hard even to approximate in general graphs). A heuristic answer is only a *claim* unless certified. This project certifies in two steps.

**Clique lower bound.** Members of a clique in H pairwise conflict, so χ(H) ≥ ω(H). In G², every radio together with all its neighbors is a clique (all are within 2 hops of each other through that radio), so ω(H) ≥ Δ(G) + 1. The project computes ω(H) exactly with Bron–Kerbosch (`nx.find_cliques`). If K = ω(H), the schedule is **proven optimal**, and the report names the clique as the witness.

For the 4×4 grid: `Node_06` has degree 8, so `Node_06` plus its 8 neighbors give ω ≥ 9, and DSATUR finds 9. Hence 9 is optimal.

**Bounded branch-and-bound (when K > ω).** The search tries to find a coloring with fewer than K slots:

- The witness clique is pre-colored 0..ω−1. This is symmetry breaking: any optimal coloring can be relabeled this way, so no solution is lost.
- Branching follows DSATUR order, with ties going to more uncolored neighbors, then node order.
- A node may only take a color c with c ≤ (colors used so far) and c < K_best − 1. This allows at most one new color and prunes any branch that cannot beat the incumbent.
- **Stopping conditions:** (a) a coloring meeting ω is found (optimal); (b) the tree is exhausted, so the incumbent is **proven optimal**; (c) the node budget (default 200,000, `--exact-budget`) is spent, so the result is reported as "best found (optimality not proven)". The search is skipped for graphs above 400 nodes to bound recursion depth.

`ring_7` shows the case where this matters. Seven radios on a ring give G = C₇ and H = C₇². That graph has ω = 3 but needs 4 colors (C_n² is 3-colorable only when 3 divides n). Every heuristic finds 4. The bound alone cannot prove that, but the search proves it in 4 search nodes.

## 6. Measured comparison

Measured from `python scripts/benchmark.py` (seed 7), range 500 m, defaults (seed 42, 100 restarts, 50 refinement passes). "Hit" means the heuristic alone reached the final, certified slot count.

| Heuristic | 16 nodes / 1.5 km (200 trials) | 40 / 2.5 km (30) | 80 / 3.5 km (30) | 150 / 5 km (30) |
|---|---|---|---|---|
| DSATUR (baseline) | 200/200 | 30/30 | 29/30 | 30/30 |
| largest_first | 198/200 | 27/30 | 26/30 | 27/30 |
| smallest_last | 199/200 | 30/30 | 30/30 | 30/30 |
| independent_set | 134/200 | 16/30 | 8/30 | 7/30 |
| connected_sequential_bfs | 188/200 | 24/30 | 23/30 | 26/30 |
| connected_sequential_dfs | 180/200 | 17/30 | 14/30 | 11/30 |
| random_order ×100 | 200/200 | 29/30 | 30/30 | 29/30 |
| **Portfolio (final)** | **200/200 proven optimal** | **30/30** | **30/30** | **30/30** |
| Median pipeline time | 8.4 ms | 24.9 ms | 59.8 ms | 136.9 ms |

Conclusions:

- **DSATUR is the right baseline.** It was optimal in every 16-node trial. On geometric (unit-disk) networks, the conflict graph's clique number is almost always reached, so DSATUR plus the clique bound certifies the result.
- **The portfolio is insurance, not decoration.** At 80 nodes DSATUR missed the optimum once, and `smallest_last` and the random restarts caught it.
- **No single alternative dominates.** `independent_set` and DFS ordering are consistently weaker on this graph class and are kept only for diversity.
- **Branch-and-bound never improved on the heuristics** in these random trials. Its value is the *proof* in non-tight cases like `ring_7` and the guarantee if a heuristic underperforms.

## 7. Complexity

Let n = radios, m = |E(G)|, Δ = max degree of G, m₂ = |E(H)| ≤ n·Δ².

| Stage | Time | Space |
|---|---|---|
| Parse | O(n log n) (sort) | O(n) |
| Build G | O(n²) distance checks | O(n + m) |
| Build H = G² | O(n·Δ²) | O(n + m₂) |
| One greedy pass | O(n + m₂) (DSATUR O((n + m₂) log n) with a heap) | O(n + m₂) |
| Portfolio | O((6 + r + p)·(n + m₂) log n), r restarts, p refinement passes | O(n + m₂) |
| Max clique | Exponential worst case; fast on sparse geometric graphs | O(n + m₂) |
| Branch-and-bound | Exponential worst case, capped by the node budget | O(n) stack |
| Validation | O(n·Δ²) (depth-2 BFS from each node) | O(n·Δ²) |

## 8. Why the answer is heuristic unless the report says "proven"

χ(H) is NP-hard to compute, so no polynomial algorithm is known to always find it. The report states one of three statuses honestly:

- `proven optimal: equals clique lower bound`
- `proven optimal: exhaustive branch-and-bound`
- `best found (optimality not proven)`: K is valid and is the best found, with a known gap of K − ω at most.

## 9. Modelling assumptions worth stating in an interview

- The radio range is a hard disk with symmetric links. Real links are probabilistic and asymmetric.
- The "two-hop" rule is the classic protocol interference model used in the TDMA and distance-2 coloring literature. It ignores accumulated interference from many distant radios, and a carrier-sense or interference range greater than the communication range. A stricter model only changes how H is built.
- One transmit slot per radio per frame (broadcast scheduling). Link scheduling (per directed link) or demand-weighted slots are natural extensions.
