"""Compare coloring heuristics on the example topologies and seeded random deployments.

Usage:  python scripts/benchmark.py [--trials 200] [--nodes 16] [--side 1500] [--seed 7]

Every number in docs/test_report.md under "Strategy comparison" comes from
running this script; nothing is hand-entered.
"""

from __future__ import annotations

import argparse
import random
import statistics
import time
from collections import Counter
from pathlib import Path

from tdma_optimizer.exact import Optimality
from tdma_optimizer.input_parser import load_coordinates_file
from tdma_optimizer.pipeline import PlanConfig, plan_schedule

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def random_deployment(rng: random.Random, nodes: int, side: float) -> dict[str, tuple[float, float]]:
    return {
        f"Node_{i + 1:02d}": (round(rng.uniform(0, side), 1), round(rng.uniform(0, side), 1))
        for i in range(nodes)
    }


def describe(name: str, coords: dict, config: PlanConfig) -> None:
    start = time.perf_counter()
    plan = plan_schedule(coords, config)
    elapsed = (time.perf_counter() - start) * 1000
    per_method = ", ".join(f"{a.method.split(' ')[0]}={a.best}" for a in plan.heuristic.attempts)
    print(f"{name:<14} n={len(coords):<3} links={plan.communication_graph.number_of_edges():<3} "
          f"LB={plan.exact.lower_bound} K={plan.num_slots} [{plan.exact.optimality.name}] "
          f"{elapsed:.0f} ms\n    {per_method}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--nodes", type=int, default=16)
    parser.add_argument("--side", type=float, default=1500.0, help="square deployment side, meters")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    config = PlanConfig()

    print("== Example topologies ==")
    for path in sorted(EXAMPLES.glob("*.json")):
        describe(path.stem, load_coordinates_file(path), config)

    print(f"\n== {args.trials} random deployments: {args.nodes} nodes in "
          f"{args.side:.0f} m x {args.side:.0f} m, range {config.radio_range:.0f} m, seed {args.seed} ==")
    rng = random.Random(args.seed)
    wins: Counter[str] = Counter()
    gaps: Counter[str] = Counter()
    sums: Counter[str] = Counter()
    outcome: Counter[str] = Counter()
    bnb_improved = 0
    times = []
    for _ in range(args.trials):
        coords = random_deployment(rng, args.nodes, args.side)
        start = time.perf_counter()
        plan = plan_schedule(coords, config)
        times.append((time.perf_counter() - start) * 1000)
        optimum_known = plan.exact.optimality is not Optimality.HEURISTIC
        outcome[plan.exact.optimality.name] += 1
        bnb_improved += plan.exact.improved
        for attempt in plan.heuristic.attempts:
            sums[attempt.method] += attempt.best
            if attempt.best == plan.num_slots:
                wins[attempt.method] += 1
            if optimum_known:
                gaps[attempt.method] += attempt.best - plan.num_slots

    print(f"{'heuristic':<34}{'mean K':>8}{'hit final K':>13}{'total excess slots':>20}")
    for method in sums:
        print(f"{method:<34}{sums[method] / args.trials:>8.2f}"
              f"{wins[method]:>9}/{args.trials:<4}{gaps[method]:>16}")
    print(f"\nfinal certificate: {dict(outcome)}")
    print(f"branch-and-bound improved on all heuristics in {bnb_improved}/{args.trials} cases")
    print(f"pipeline time per topology: median {statistics.median(times):.1f} ms, "
          f"max {max(times):.1f} ms")


if __name__ == "__main__":
    main()
