import unittest

import networkx as nx

from tdma_optimizer.conflict_graph import build_conflict_graph, conflict_stats
from tdma_optimizer.validator import pairs_within_two_hops

from tests.helpers import graphs_for, grid_16, line, random_coords


class ConflictRules(unittest.TestCase):
    def test_direct_link_is_conflict(self):
        _, h = graphs_for(line(2))
        self.assertTrue(h.has_edge("A", "B"))
        self.assertEqual(h.edges["A", "B"]["hops"], 1)

    def test_two_hop_hidden_terminal_is_conflict(self):
        g, h = graphs_for(line(3))
        self.assertFalse(g.has_edge("A", "C"))  # A and C cannot hear each other...
        self.assertTrue(h.has_edge("A", "C"))  # ...but they collide at B
        self.assertEqual(h.edges["A", "C"]["hops"], 2)

    def test_three_hops_apart_not_in_conflict(self):
        _, h = graphs_for(line(4))  # A -- B -- C -- D
        self.assertFalse(h.has_edge("A", "D"))
        self.assertTrue(h.has_edge("A", "C"))
        self.assertTrue(h.has_edge("B", "D"))

    def test_disconnected_components_never_conflict(self):
        coords = {"A": (0, 0), "B": (400, 0), "C": (10_000, 0), "D": (10_400, 0)}
        _, h = graphs_for(coords)
        self.assertEqual(set(map(frozenset, h.edges)), {frozenset("AB"), frozenset("CD")})

    def test_no_edges_gives_empty_conflict_graph(self):
        _, h = graphs_for({f"N{i}": (i * 2000.0, 0.0) for i in range(4)})
        self.assertEqual(h.number_of_nodes(), 4)
        self.assertEqual(h.number_of_edges(), 0)

    def test_node_attributes_preserved(self):
        g, h = graphs_for(line(3))
        self.assertEqual(h.nodes["B"]["pos"], g.nodes["B"]["pos"])
        self.assertEqual(list(h.nodes), list(g.nodes))


class MatchesHopDistance(unittest.TestCase):
    """nx.power(G, 2) must equal "hop distance 1 or 2", checked against an independent BFS."""

    def test_equals_bfs_pairs_on_random_topologies(self):
        for seed in range(25):
            with self.subTest(seed=seed):
                g, h = graphs_for(random_coords(seed))
                bfs = {frozenset(p): hops for p, hops in pairs_within_two_hops(g).items()}
                power = {frozenset((u, v)): d for u, v, d in h.edges(data="hops")}
                self.assertEqual(power, bfs)

    def test_grid_stats(self):
        _, h = graphs_for(grid_16())
        stats = conflict_stats(h)
        self.assertEqual((stats.total, stats.one_hop, stats.two_hop), (90, 42, 48))

    def test_coloring_g_alone_is_insufficient(self):
        # Proper coloring of G can put A and C in the same slot -> collision at B.
        g, h = graphs_for(line(3))
        coloring_of_g = nx.coloring.greedy_color(g, strategy="largest_first")
        self.assertEqual(coloring_of_g["A"], coloring_of_g["C"])
        coloring_of_h = nx.coloring.greedy_color(h, strategy="largest_first")
        self.assertNotEqual(coloring_of_h["A"], coloring_of_h["C"])

    def test_build_is_pure(self):
        g, _ = graphs_for(line(3))
        before = list(g.edges)
        build_conflict_graph(g)
        self.assertEqual(list(g.edges), before)


if __name__ == "__main__":
    unittest.main()
