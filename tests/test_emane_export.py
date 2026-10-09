import unittest
import xml.etree.ElementTree as ET

from tdma_optimizer.emane_export import EmaneRadioParams, build_schedule_xml, nem_id_map
from tdma_optimizer.errors import InputValidationError
from tdma_optimizer.pipeline import plan_schedule

from tests.helpers import grid_16


class EmaneExport(unittest.TestCase):
    def setUp(self):
        self.plan = plan_schedule(grid_16())
        self.root = ET.fromstring(build_schedule_xml(self.plan.assignment, self.plan.node_order))

    def test_structure_matches_schedule(self):
        self.assertEqual(self.root.tag, "emane-tdma-schedule")
        structure = self.root.find("structure")
        self.assertEqual(structure.get("slots"), str(self.plan.num_slots))
        self.assertEqual(structure.get("frames"), "1")
        self.assertEqual(structure.get("slotduration"), "1000")  # 1 ms in microseconds

    def test_each_nem_transmits_in_exactly_its_slot(self):
        nems = nem_id_map(self.plan.node_order)
        seen: dict[int, int] = {}
        for slot in self.root.iter("slot"):
            self.assertIsNotNone(slot.find("tx"))
            for nem in slot.get("nodes").split(","):
                self.assertNotIn(int(nem), seen)
                seen[int(nem)] = int(slot.get("index"))
        self.assertEqual(seen, {nems[n]: s for n, s in self.plan.assignment.items()})

    def test_nem_ids_start_at_one_in_node_order(self):
        self.assertEqual(nem_id_map(["Node_01", "Node_02"]), {"Node_01": 1, "Node_02": 2})

    def test_custom_parameters(self):
        xml = build_schedule_xml({"A": 0}, ["A"], EmaneRadioParams(slot_duration_us=500, frequency="1.2G"))
        root = ET.fromstring(xml)
        self.assertEqual(root.find("structure").get("slotduration"), "500")
        self.assertEqual(root.find("multiframe").get("frequency"), "1.2G")

    def test_rejects_mismatched_inputs(self):
        with self.assertRaises(InputValidationError):
            build_schedule_xml({"A": 0}, ["A", "B"])
        with self.assertRaises(InputValidationError):
            build_schedule_xml({"A": 0}, ["A"], EmaneRadioParams(slot_duration_us=0))


if __name__ == "__main__":
    unittest.main()
