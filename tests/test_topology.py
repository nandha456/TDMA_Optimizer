import math
import unittest

import networkx as nx

from tdma_optimizer.errors import InputValidationError
from tdma_optimizer.topology import build_communication_graph, connected_components


class EdgeConstruction(unittest.TestCase):
    def test_exactly_500m_creates_edge(self):
        g = build_communication_graph({"A": (0.0, 0.0), "B": (500.0, 0.0)}, 500.0)
        self.assertTrue(g.has_edge("A", "B"))

    def test_beyond_500m_no_edge(self):
        g = build_communication_graph({"A": (0.0, 0.0), "B": (500.001, 0.0)}, 500.0)
        self.assertFalse(g.has_edge("A", "B"))

    def test_horizontal_vertical_diagonal_distances(self):
        coords = {"O": (0.0, 0.0), "H": (450.0, 0.0), "V": (0.0, -450.0), "D": (300.0, 400.0)}
        g = build_communication_graph(coords, 500.0)
        self.assertAlmostEqual(g.edges["O", "H"]["distance"], 450.0)
        self.assertAlmostEqual(g.edges["O", "V"]["distance"], 450.0)
        self.assertEqual(g.edges["O", "D"]["distance"], 500.0)  # 3-4-5 triangle, exact boundary
        self.assertFalse(g.has_edge("H", "V"))  # 450*sqrt(2) ~ 636 m
        self.assertAlmostEqual(math.dist(coords["H"], coords["V"]), 450 * math.sqrt(2))

    def test_range_is_configurable(self):
        coords = {"A": (0.0, 0.0), "B": (700.0, 0.0)}
        self.assertFalse(build_communication_graph(coords, 500.0).has_edge("A", "B"))
        self.assertTrue(build_communication_graph(coords, 700.0).has_edge("A", "B"))

    def test_node_attributes_and_no_self_loops(self):
        g = build_communication_graph({"A": (1.0, 2.0), "B": (3.0, 4.0)}, 500.0)
        self.assertEqual(g.nodes["A"]["pos"], (1.0, 2.0))
        self.assertEqual(nx.number_of_selfloops(g), 0)
        self.assertEqual(g.number_of_edges(), 1)

    def test_duplicate_coordinates_are_linked(self):
        g = build_communication_graph({"A": (5.0, 5.0), "B": (5.0, 5.0)}, 500.0)
        self.assertTrue(g.has_edge("A", "B"))
        self.assertEqual(g.edges["A", "B"]["distance"], 0.0)

    def test_no_edges_when_all_far_apart(self):
        coords = {f"N{i}": (i * 1000.0, 0.0) for i in range(5)}
        g = build_communication_graph(coords, 500.0)
        self.assertEqual(g.number_of_nodes(), 5)
        self.assertEqual(g.number_of_edges(), 0)

    def test_invalid_range_rejected(self):
        for bad in (0, -1, float("nan"), float("inf"), True, "500"):
            with self.subTest(bad=bad), self.assertRaises(InputValidationError):
                build_communication_graph({"A": (0.0, 0.0)}, bad)  # type: ignore[arg-type]


class Components(unittest.TestCase):
    def test_disconnected_components_reported(self):
        coords = {"A": (0, 0), "B": (400, 0), "C": (5000, 0), "D": (5400, 0), "E": (9000, 0)}
        g = build_communication_graph(coords, 500.0)
        self.assertEqual(connected_components(g), [["A", "B"], ["C", "D"], ["E"]])


if __name__ == "__main__":
    unittest.main()
