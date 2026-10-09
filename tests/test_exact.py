import json
import unittest

import networkx as nx

from tdma_optimizer.coloring import count_slots, is_proper
from tdma_optimizer.exact import Optimality, certify, clique_lower_bound
from tdma_optimizer.input_parser import parse_coordinates

from tests.helpers import EXAMPLES, graphs_for, grid_16


class LowerBound(unittest.TestCase):
    def test_grid_clique_is_9(self):
        _, h = graphs_for(grid_16())
        size, witness = clique_lower_bound(h)
        self.assertEqual(size, 9)
        self.assertTrue(all(h.has_edge(u, v) for u in witness for v in witness if u != v))

    def test_clique_bound_at_least_max_degree_plus_one(self):
        g, h = graphs_for(grid_16())
        self.assertGreaterEqual(clique_lower_bound(h)[0], max(d for _, d in g.degree) + 1)

    def test_empty_graph(self):
        self.assertEqual(clique_lower_bound(nx.Graph()), (0, ()))


class Certify(unittest.TestCase):
    def test_heuristic_meeting_bound_is_proven_by_clique(self):
        _, h = graphs_for(grid_16())
        coloring = nx.coloring.greedy_color(h, strategy="saturation_largest_first")
        result = certify(h, coloring)
        self.assertIs(result.optimality, Optimality.PROVEN_BY_CLIQUE)
        self.assertEqual(result.search_nodes, 0)

    def test_ring_of_7_proven_by_search(self):
        # C7 squared: largest clique 3, but chromatic number 4 (7 is not divisible by 3).
        coords = parse_coordinates((EXAMPLES / "ring_7.json").read_text())
        g, h = graphs_for(coords)
        self.assertEqual(g.number_of_edges(), 7)
        coloring = nx.coloring.greedy_color(h, strategy="saturation_largest_first")
        result = certify(h, coloring)
        self.assertEqual(result.lower_bound, 3)
        self.assertEqual(result.num_slots, 4)
        self.assertIs(result.optimality, Optimality.PROVEN_BY_SEARCH)

    def test_search_improves_a_poor_incumbent(self):
        _, h = graphs_for(grid_16())
        terrible = {node: i for i, node in enumerate(h.nodes)}  # 16 slots
        result = certify(h, terrible)
        self.assertTrue(result.improved)
        self.assertEqual(result.num_slots, 9)
        self.assertTrue(is_proper(h, result.assignment))

    def test_search_finds_optimum_on_odd_cycle_power(self):
        h = nx.cycle_graph(8)  # treat directly as a conflict graph: C8, chi = 2
        h = nx.relabel_nodes(h, {i: f"n{i}" for i in range(8)})
        result = certify(h, {n: i for i, n in enumerate(h.nodes)})
        self.assertEqual(result.num_slots, 2)
        self.assertIs(result.optimality, Optimality.PROVEN_BY_CLIQUE)

    def test_budget_exhaustion_reports_heuristic(self):
        coords = parse_coordinates((EXAMPLES / "ring_7.json").read_text())
        _, h = graphs_for(coords)
        coloring = nx.coloring.greedy_color(h, strategy="saturation_largest_first")
        result = certify(h, coloring, node_budget=1)
        self.assertIs(result.optimality, Optimality.HEURISTIC)
        self.assertEqual(count_slots(result.assignment), count_slots(coloring))

    def test_zero_budget_disables_search(self):
        coords = json.loads((EXAMPLES / "ring_7.json").read_text())
        _, h = graphs_for({k: tuple(v) for k, v in coords.items()})
        result = certify(h, nx.coloring.greedy_color(h), node_budget=0)
        self.assertIs(result.optimality, Optimality.HEURISTIC)
        self.assertEqual(result.search_nodes, 0)


if __name__ == "__main__":
    unittest.main()
