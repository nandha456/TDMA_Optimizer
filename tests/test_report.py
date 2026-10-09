import re
import unittest

from tdma_optimizer.pipeline import plan_schedule
from tdma_optimizer.report import build_slot_matrix, column_labels, render_matrix, render_report

from tests.helpers import grid_16, random_coords


class SlotMatrix(unittest.TestCase):
    def setUp(self):
        self.plan = plan_schedule(grid_16())
        self.nodes = self.plan.node_order
        self.matrix = build_slot_matrix(self.plan.assignment, self.nodes)

    def test_every_node_has_exactly_one_transmit_slot(self):
        for col, node in enumerate(self.nodes):
            self.assertEqual(sum(row[col] for row in self.matrix), 1, node)

    def test_matrix_agrees_with_mapping(self):
        for slot, row in enumerate(self.matrix):
            for col, node in enumerate(self.nodes):
                self.assertEqual(row[col] == 1, self.plan.assignment[node] == slot)

    def test_rows_are_numeric_slots_and_nodes_in_header_once(self):
        text = render_matrix(self.plan.assignment, self.nodes)
        slot_ids = [int(m) for m in re.findall(r"^Slot (\d+)", text, flags=re.M)]
        self.assertEqual(slot_ids, list(range(self.plan.num_slots)))
        header = next(line for line in text.splitlines() if line.startswith("Slot \\ Node"))
        cells = [c.strip() for c in header.split("|")[1:]]
        self.assertEqual(cells, [n.removeprefix("Node_") for n in self.nodes])

    def test_printed_matrix_matches_mapping(self):
        report = render_report(self.plan)
        mapping = {m[0]: int(m[1]) for m in re.findall(r"^\s+(Node_\d+) : Slot (\d+)$", report, flags=re.M)}
        self.assertEqual(mapping, self.plan.assignment)
        rows = re.findall(r"^Slot (\d+)\s+\|(.*)$", report, flags=re.M)
        for slot, cells in rows:
            bits = [int(c) for c in cells.split("|")]
            for node, bit in zip(self.nodes, bits):
                self.assertEqual(bit == 1, mapping[node] == int(slot))

    def test_report_contents(self):
        report = render_report(self.plan)
        for expected in ("Total Nodes Processed", "500.0 meters", "9 unique timeslots",
                         "saturation_largest_first", "verified conflict-free", "Connected components"):
            self.assertIn(expected, report)


class Labels(unittest.TestCase):
    def test_prefix_stripped_only_when_safe(self):
        self.assertEqual(column_labels(["Node_1", "Node_10", "Node_11"]), (["1", "10", "11"], "Node_"))
        self.assertEqual(column_labels(["A", "B"]), (["A", "B"], ""))
        self.assertEqual(column_labels(["Solo"]), (["Solo"], ""))

    def test_random_topology_matrix_is_consistent(self):
        plan = plan_schedule(random_coords(11))
        matrix = build_slot_matrix(plan.assignment, plan.node_order)
        self.assertEqual(len(matrix), plan.num_slots)
        self.assertEqual(sum(map(sum, matrix)), 16)


if __name__ == "__main__":
    unittest.main()
