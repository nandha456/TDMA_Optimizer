import unittest

from tdma_optimizer.validator import pairs_within_two_hops, validate_schedule

from tests.helpers import graphs_for, grid_16, line

# The illustrative "Sample Output" printed in the assessment PDF (5 slots).
PDF_SAMPLE_ASSIGNMENT = {
    "Node_01": 0, "Node_02": 1, "Node_03": 0, "Node_04": 1, "Node_05": 2, "Node_06": 3,
    "Node_07": 2, "Node_08": 3, "Node_09": 0, "Node_10": 1, "Node_11": 4, "Node_12": 1,
    "Node_13": 2, "Node_14": 3, "Node_15": 2, "Node_16": 3,
}


class Validator(unittest.TestCase):
    def test_valid_schedule_accepted(self):
        g, _ = graphs_for(line(4))
        result = validate_schedule(g, {"A": 0, "B": 1, "C": 2, "D": 0})
        self.assertTrue(result.is_valid)
        self.assertEqual(result.errors, ())
        self.assertEqual(result.pairs_checked, 5)  # AB BC CD AC BD

    def test_direct_link_conflict_rejected(self):
        g, _ = graphs_for(line(2))
        result = validate_schedule(g, {"A": 0, "B": 0})
        self.assertFalse(result.is_valid)
        self.assertEqual([(v.node_a, v.node_b, v.hops) for v in result.violations], [("A", "B", 1)])

    def test_hidden_terminal_conflict_rejected(self):
        g, _ = graphs_for(line(3))
        result = validate_schedule(g, {"A": 0, "B": 1, "C": 0})
        self.assertFalse(result.is_valid)
        self.assertEqual([(v.node_a, v.node_b, v.hops) for v in result.violations], [("A", "C", 2)])
        self.assertIn("hidden terminal", result.errors[0])

    def test_missing_and_unknown_nodes_rejected(self):
        g, _ = graphs_for(line(3))
        result = validate_schedule(g, {"A": 0, "B": 1, "Z": 2})
        self.assertFalse(result.is_valid)
        self.assertTrue(any("without a slot: C" in e for e in result.errors))
        self.assertTrue(any("unknown nodes: Z" in e for e in result.errors))

    def test_bad_slot_values_rejected(self):
        g, _ = graphs_for({"A": (0, 0)})
        for bad in (-1, 1.0, "0", True, None):
            with self.subTest(bad=bad):
                self.assertFalse(validate_schedule(g, {"A": bad}).is_valid)

    def test_pdf_sample_output_is_not_valid_for_the_pdf_grid(self):
        # Node_01 (0,0) and Node_03 (600,0) share neighbour Node_02 yet both get slot 0.
        g, _ = graphs_for(grid_16())
        result = validate_schedule(g, PDF_SAMPLE_ASSIGNMENT)
        self.assertFalse(result.is_valid)
        pairs = {(v.node_a, v.node_b) for v in result.violations}
        self.assertIn(("Node_01", "Node_03"), pairs)

    def test_pairs_within_two_hops_ignores_three_hops(self):
        g, _ = graphs_for(line(4))
        self.assertNotIn(("A", "D"), pairs_within_two_hops(g))


if __name__ == "__main__":
    unittest.main()
