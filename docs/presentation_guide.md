# Presentation and Defense Guide

## Suggested 10-minute flow

1. **Problem (1 min).** Radios share one channel and take turns. A collision happens at the *receiver*. Two rules follow: neighbors differ, and neighbors-of-neighbors differ. Draw A – B – C.
2. **Key insight (1 min).** "Within two hops" is exactly an edge of G². Scheduling becomes coloring G², and the frame length becomes χ(G²).
3. **Pipeline (1 min).** Parse → G → H → heuristics → certificate → independent validation → report and EMANE XML.
4. **Live demo (3 min).**
   - `tdma-optimizer --input examples/grid_16.json` → 9 slots, *proven optimal*.
   - Point at the clique `Node_06` + 8 neighbors: "no schedule can do better than 9."
   - `tdma-optimizer --input examples/field_16.json` → 16 radios in 4 slots, 4× reuse across 2 components.
   - `tdma-optimizer --input examples/ring_7.json --expected-nodes 7` → bound says 3, search proves 4.
   - `--coordinates '{bad'` → clean error, exit 2.
5. **Evidence (2 min).** 94 tests, mutation check, and the benchmark table (DSATUR optimal in 200/200 random 16-node cases).
6. **Part 2 (1.5 min).** XML bridge works now. Next is a pathloss table from G plus an experiment against a G-only "control" schedule.
7. **Limitations (0.5 min).** Protocol interference model, static topology, one slot per node.

## The one point to raise before they do

The PDF's sample output shows **5 slots**. For the PDF's own example coordinates (a 4×4 grid at 300 m), **9 is a proven lower bound**: the 500 m range reaches diagonal neighbors at 424 m, so an interior node plus its 8 neighbors are pairwise within 2 hops. The sample also assigns `Node_01` and `Node_03` the same slot while both neighbor `Node_02`, which is a hidden-terminal collision. Present it as: "I treated the sample as a format illustration. My validator rejects it for that grid, and there is a test showing exactly which pairs collide." Raise it calmly and with the evidence, not as a gotcha.

## Likely questions and defensible answers

**Why color G² instead of G?**
Coloring G only separates direct neighbors. A and C in A – B – C are not neighbors, so they could share a slot and collide at B. G² adds exactly the 2-hop edges. There is a test showing NetworkX's greedy coloring of G giving A = C.

**Why is 3 hops safe?**
At 3+ hops, A and D have no common neighbor. No radio is in range of both, so no receiver ever hears them overlap.

**Is your answer optimal?**
Only when the report says "proven". The clique of H is a lower bound. When the heuristic matches it, that is a proof. Otherwise a bounded branch-and-bound either proves optimality or the report says "best found". On all 290 random topologies tried, the result was proven optimal.

**The problem is NP-hard. How can you prove optimality?**
NP-hard is a worst-case statement. Specific instances, especially small geometric ones, are often easy. The clique bound is tight on unit-disk graph squares almost always, and the branch-and-bound handles the rest under a node budget.

**Why DSATUR as the baseline?**
It colors the most constrained node first (the one whose neighbors already use the most colors). It is exact on bipartite graphs and the standard strong greedy. Measured: optimal in 200/200 random 16-node trials.

**Then why run other heuristics?**
Insurance. At 80 nodes DSATUR missed once, and smallest-last and the random restarts caught it. All attempts take milliseconds, and ties always keep DSATUR's result, so the portfolio can only help.

**What is iterated greedy, and why can it not make things worse?**
Re-run greedy, visiting nodes one old color class at a time. Each class is an independent set, so the j-th class revisited can always use a color ≤ j. K never increases.

**How do you make random runs reproducible?**
A single `random.Random(seed)` instance is passed through. NetworkX's global randomness is never used. Nodes are inserted in natural order. Same seed gives byte-identical output, and a test asserts this.

**Why a separate validator? Is that not redundant?**
It is deliberately independent. It recomputes the 1-hop and 2-hop pairs with BFS on G rather than trusting `nx.power`, so a bug in building H cannot validate itself. The pipeline refuses to print an invalid schedule, and a test injects a broken optimizer to prove that.

**What is the complexity?**
G is O(n²) pair checks. H is O(n·Δ²). Each greedy pass is roughly O((n + m₂) log n). The clique search and branch-and-bound are exponential in the worst case but bounded and fast here: about 8 ms for 16 nodes and about 140 ms for 150 nodes.

**What happens exactly at 500 m?**
Inclusive, compared exactly, as specified. (0,0) to (300,400) is exactly 500.0, so they are linked. There is a test for it.

**Two radios at the same coordinates?**
Distance 0 is within range, so they are linked and must get different slots. Physically, co-located radios certainly interfere.

**Disconnected networks?**
Separate components never conflict, so they reuse slots freely. `field_16` has 2 components using the same 4 slots.

**How does this connect to EMANE?**
`--emane-xml` writes a full TDMA schedule: 1 frame, K slots of 1000 µs, one `<tx/>` slot per NEM, with every other slot defaulting to receive. It is delivered with `emaneevent-tdmaschedule`. To make EMANE agree with G, publish pathloss events derived from the same distances. Validation compares EMANE's per-slot RX and TX tables, and a control run that colors G only should show collisions at the shared neighbor.

**What did you not model?**
SINR and aggregate interference, interference range larger than decode range, asymmetric links, mobility, and traffic demand. Each one changes how H is built or adds weights; the coloring core stays.

**How would you handle mobility?**
Recompute periodically or on topology change. Send an EMANE *update* schedule for the nodes whose slots changed. A local repair that recolors only nodes whose 2-hop neighborhood changed keeps churn low.

**How would you give a busy relay more airtime?**
Give node v a demand of d(v) slots by expanding it into d(v) mutually conflicting copies in H, then color as before. The frame grows, but relays get proportional airtime.

**Why NetworkX and not your own coloring?**
Its strategies are tested and recognizable to a reviewer, so time went into the parts that matter: the constraint model, certification and validation. The parts it lacks (seeded random orders, iterated greedy, branch-and-bound) are implemented here and tested.

**What would you change with more time?**
Add the EMANE pathloss generator and run the experiment, use a demand-weighted slot model, add local repair for mobility, and replace the O(n²) edge scan with a grid index for large deployments.

## Numbers to remember

| Metric | Value |
|---|---|
| Grid-16 slots | 9 (proven; clique = `Node_06` + 8 neighbors) |
| Grid-16 links / conflicts | 42 links; 90 conflict pairs = 42 one-hop + 48 two-hop |
| Field-16 slots | 4 (reuse factor 4.0, 2 components) |
| Ring-7 | bound 3, optimum 4, proven by search |
| Tests | 94 passing; 7 of 9 injected bugs caught, the other 2 performance-only |
| Random 16-node trials | 200/200 proven optimal, mean 7.67 slots, median 8.4 ms |
