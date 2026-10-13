import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from tdma_optimizer.emane_scenario import (
    g_only_coloring,
    main,
    predict_delivery,
    write_scenario,
)
from tdma_optimizer.pipeline import plan_schedule
from tdma_optimizer.validator import validate_schedule

from tests.helpers import EXAMPLES, graphs_for, grid_16, line


class Prediction(unittest.TestCase):
    def test_valid_schedule_predicts_every_link_delivered(self):
        plan = plan_schedule(grid_16())
        outcomes = predict_delivery(plan.communication_graph, plan.assignment)
        self.assertEqual(len(outcomes), 2 * plan.communication_graph.number_of_edges())
        self.assertTrue(all(o.delivered for o in outcomes))

    def test_hidden_terminal_predicts_collision_at_middle(self):
        g, _ = graphs_for(line(3))  # A - B - C, A and C share a slot
        outcomes = {(o.src, o.dst): o for o in predict_delivery(g, {"A": 0, "B": 1, "C": 0})}
        self.assertFalse(outcomes["A", "B"].delivered)
        self.assertEqual(outcomes["A", "B"].reason, "collision with C")
        self.assertTrue(outcomes["B", "A"].delivered)

    def test_same_slot_neighbours_predict_receiver_transmitting(self):
        g, _ = graphs_for(line(2))
        outcomes = predict_delivery(g, {"A": 0, "B": 0})
        self.assertEqual({o.reason for o in outcomes}, {"receiver transmitting"})

    def test_prediction_agrees_with_validator(self):
        # Every link delivered  <=>  schedule passes the distance-2 validator.
        g, _ = graphs_for(grid_16())
        for assignment in (plan_schedule(grid_16()).assignment, g_only_coloring(g)):
            all_ok = all(o.delivered for o in predict_delivery(g, assignment))
            self.assertEqual(all_ok, validate_schedule(g, assignment).is_valid)

    def test_g_only_control_is_proper_on_g_but_not_on_g_squared(self):
        g, _ = graphs_for(grid_16())
        control = g_only_coloring(g)
        self.assertTrue(all(control[u] != control[v] for u, v in g.edges))
        self.assertFalse(validate_schedule(g, control).is_valid)
        lost = [o for o in predict_delivery(g, control) if not o.delivered]
        self.assertEqual(len(lost), 64)


class ScenarioFiles(unittest.TestCase):
    def test_writes_complete_scenario(self):
        plan = plan_schedule(grid_16())
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            scenario = write_scenario(out, "optimized", plan.communication_graph,
                                      plan.assignment, plan.node_order, slot_us=4000)
            for name in ("tdmanem.xml", "tdmaradiomodel.xml", "transvirtual.xml",
                         "schedule.xml", "scenario.json"):
                self.assertTrue((out / name).exists(), name)
            self.assertEqual(len(list(out.glob("platform-*.xml"))), 16)
            platform = (out / "platform-07.xml").read_text()
            self.assertIn('<nem id="7"', platform)
            self.assertIn('value="0.0.0.0:47007"', platform)
            ET.fromstring(platform.split("\n", 2)[2])  # well-formed after the DOCTYPE
            schedule = ET.parse(out / "schedule.xml").getroot()
            self.assertEqual(schedule.find("structure").get("slotduration"), "4000")
            self.assertEqual(scenario["num_slots"], 9)
            self.assertEqual(json.loads((out / "scenario.json").read_text())["label"], "optimized")

    def test_cli_writes_both_scenarios(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main(["--input", str(EXAMPLES / "grid_16.json"), "--out", tmp])
            self.assertEqual(code, 0)
            for label, slots in (("optimized", 9), ("control-g-only", 4)):
                data = json.loads((Path(tmp) / label / "scenario.json").read_text())
                self.assertEqual(data["num_slots"], slots)

    def test_cli_rejects_bad_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["--input", "/nope.json", "--out", tmp]), 2)


if __name__ == "__main__":
    unittest.main()
