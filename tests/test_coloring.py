import random
import unittest

import networkx as nx

from tdma_optimizer.coloring import (
    BASELINE_STRATEGY,
    DETERMINISTIC_STRATEGIES,
    count_slots,
    is_proper,
    iterated_greedy,
    normalize_slots,
    optimize_schedule,
)
from tdma_optimizer.validator import validate_schedule

from tests.helpers import graphs_for, grid_16, line, random_coords


class OptimizeSchedule(unittest.TestCase):
    def test_valid_coloring_for_nontrivial_graph(self):
        g, h = graphs_for(grid_16())
        result = optimize_schedule(h, seed=42, restarts=50)
        self.assertTrue(validate_schedule(g, result.assignment).is_valid)
        self.assertEqual(set(result.assignment), set(g.nodes))
        self.assertEqual(result.num_slots, 9)  # 9 is a proven lower bound for this grid

    def test_slots_are_contiguous_from_zero(self):
        for seed in range(10):
            _, h = graphs_for(random_coords(seed))
            result = optimize_schedule(h, seed=seed, restarts=20)
            self.assertEqual(set(result.assignment.values()), set(range(result.num_slots)))

    def test_same_seed_is_reproducible(self):
        _, h = graphs_for(random_coords(3, n=30, side=2000))
        a = optimize_schedule(h, seed=123, restarts=40)
        b = optimize_schedule(h, seed=123, restarts=40)
        self.assertEqual(a.assignment, b.assignment)
        self.assertEqual(a.attempts, b.attempts)

    def test_best_is_never_worse_than_any_attempt_or_baseline(self):
        for seed in range(15):
            _, h = graphs_for(random_coords(seed, n=30, side=2200))
            result = optimize_schedule(h, seed=seed, restarts=30)
            self.assertEqual(result.attempts[0].method, BASELINE_STRATEGY)
            self.assertLessEqual(result.num_slots, min(a.best for a in result.attempts))

    def test_selection_alone_picks_minimum_attempt(self):
        # With refinement off, the result must equal the best raw attempt. Guards the
        # selection rule itself, which later stages could otherwise mask.
        for seed in range(15):
            _, h = graphs_for(random_coords(seed, n=40, side=2500))
            result = optimize_schedule(h, seed=seed, restarts=30, refine_passes=0)
            self.assertEqual(result.num_slots, min(a.best for a in result.attempts))

    def test_all_deterministic_strategies_attempted(self):
        _, h = graphs_for(line(5))
        methods = [a.method for a in optimize_schedule(h, restarts=3).attempts]
        for strategy in DETERMINISTIC_STRATEGIES:
            self.assertIn(strategy, methods)

    def test_spatial_reuse_on_chain(self):
        # A-B-C-D: A and D are 3 hops apart, so 3 slots suffice for 4 radios.
        g, h = graphs_for(line(4))
        result = optimize_schedule(h, restarts=10)
        self.assertEqual(result.num_slots, 3)
        self.assertEqual(result.assignment["A"], result.assignment["D"])
        self.assertTrue(validate_schedule(g, result.assignment).is_valid)

    def test_disconnected_components_reuse_slots(self):
        coords = {"A": (0, 0), "B": (400, 0), "C": (10_000, 0), "D": (10_400, 0)}
        _, h = graphs_for(coords)
        self.assertEqual(optimize_schedule(h, restarts=5).num_slots, 2)

    def test_no_edges_needs_one_slot(self):
        _, h = graphs_for({f"N{i}": (i * 2000.0, 0.0) for i in range(6)})
        result = optimize_schedule(h, restarts=5)
        self.assertEqual(result.num_slots, 1)
        self.assertEqual(set(result.assignment.values()), {0})

    def test_zero_restarts_still_works(self):
        _, h = graphs_for(grid_16())
        self.assertEqual(optimize_schedule(h, restarts=0, refine_passes=0).num_slots, 9)

    def test_negative_restarts_rejected(self):
        _, h = graphs_for(line(3))
        with self.assertRaises(ValueError):
            optimize_schedule(h, restarts=-1)


class Helpers(unittest.TestCase):
    def test_normalize_preserves_conflicts(self):
        g = nx.path_graph(["a", "b", "c", "d"])
        raw = {"a": 7, "b": 3, "c": 7, "d": 11}
        norm = normalize_slots(raw, ["a", "b", "c", "d"])
        self.assertEqual(norm, {"a": 0, "b": 1, "c": 0, "d": 2})
        for u, v in [("a", "b"), ("a", "c"), ("b", "d"), ("a", "d")]:
            self.assertEqual(raw[u] == raw[v], norm[u] == norm[v])
        self.assertTrue(is_proper(g, norm))

    def test_iterated_greedy_never_increases_slots(self):
        for seed in range(10):
            _, h = graphs_for(random_coords(seed, n=40, side=2500))
            rng = random.Random(seed)
            order = list(h.nodes)
            rng.shuffle(order)
            start = nx.coloring.greedy_color(h, strategy=lambda _g, _c: iter(order))
            refined = iterated_greedy(h, start, rng, passes=20)
            self.assertTrue(is_proper(h, refined))
            self.assertLessEqual(count_slots(refined), count_slots(start))

    def test_is_proper_detects_missing_node_and_clash(self):
        g = nx.path_graph(3)
        self.assertFalse(is_proper(g, {0: 0, 1: 1}))
        self.assertFalse(is_proper(g, {0: 0, 1: 0, 2: 1}))


if __name__ == "__main__":
    unittest.main()
