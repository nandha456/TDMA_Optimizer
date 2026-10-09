"""End-to-end tests through the CLI entry point (in-process) and as a real subprocess."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from unittest import mock

from tdma_optimizer.cli import EXIT_INPUT_ERROR, EXIT_OK, main
import tdma_optimizer.pipeline as pipeline_module
from tdma_optimizer.errors import ScheduleValidationError
from tdma_optimizer.pipeline import plan_schedule
from tdma_optimizer.validator import validate_schedule

from tests.helpers import EXAMPLES, as_json, grid_16, random_coords


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as exc:  # argparse usage errors
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class EndToEnd(unittest.TestCase):
    def test_16_node_file_input(self):
        code, out, _ = run_cli("--input", str(EXAMPLES / "grid_16.json"), "--seed", "42", "--restarts", "100")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("9 unique timeslots", out)
        self.assertIn("verified conflict-free", out)

    def test_inline_json_small_topology(self):
        coords = '{"Node_01":[0.0,0.0],"Node_02":[300.0,0.0],"Node_03":[600.0,0.0],"Node_04":[300.0,400.0]}'
        code, out, _ = run_cli("--coordinates", coords, "--expected-nodes", "4")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("Total Nodes Processed", out)

    def test_wrong_node_count_fails(self):
        code, _, err = run_cli("--input", str(EXAMPLES / "grid_16.json"), "--expected-nodes", "4")
        self.assertEqual(code, EXIT_INPUT_ERROR)
        self.assertIn("Expected 4 nodes but received 16", err)

    def test_invalid_json_fails_cleanly(self):
        code, out, err = run_cli("--coordinates", "{bad", "--expected-nodes", "1")
        self.assertEqual(code, EXIT_INPUT_ERROR)
        self.assertEqual(out, "")
        self.assertIn("Invalid JSON", err)

    def test_input_methods_are_mutually_exclusive(self):
        code, _, err = run_cli("--input", "x.json", "--coordinates", "{}")
        self.assertEqual(code, 2)
        self.assertIn("not allowed with", err)

    def test_an_input_method_is_required(self):
        code, _, _ = run_cli()
        self.assertEqual(code, 2)

    def test_invalid_range_fails(self):
        code, _, err = run_cli("--input", str(EXAMPLES / "grid_16.json"), "--range", "-5")
        self.assertEqual(code, EXIT_INPUT_ERROR)
        self.assertIn("positive", err)

    def test_no_edges_topology(self):
        coords = as_json({f"N{i}": (i * 1000.0, 0.0) for i in range(5)})
        code, out, _ = run_cli("--coordinates", coords, "--expected-nodes", "5")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("1 unique timeslots", out)

    def test_same_seed_same_output(self):
        args = ("--coordinates", as_json(random_coords(5)), "--seed", "9", "--restarts", "30")
        self.assertEqual(run_cli(*args)[1], run_cli(*args)[1])

    def test_emane_xml_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "schedule.xml"
            code, out, _ = run_cli("--input", str(EXAMPLES / "grid_16.json"), "--emane-xml", str(path))
            self.assertEqual(code, EXIT_OK)
            self.assertEqual(ET.parse(path).getroot().find("structure").get("slots"), "9")
            self.assertIn("Node_16 -> NEM 16", out)

    def test_module_entry_point_subprocess(self):
        proc = subprocess.run(
            [sys.executable, "-m", "tdma_optimizer", "--input", str(EXAMPLES / "field_16.json")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("TDMA TOPOLOGY OPTIMIZATION REPORT", proc.stdout)


class Pipeline(unittest.TestCase):
    def test_random_16_node_topologies_are_valid(self):
        for seed in range(40):
            with self.subTest(seed=seed):
                plan = plan_schedule(random_coords(seed))
                self.assertTrue(validate_schedule(plan.communication_graph, plan.assignment).is_valid)
                self.assertGreaterEqual(plan.num_slots, plan.exact.lower_bound)

    def test_validation_gate_is_wired(self):
        # Simulate an optimizer bug: the pipeline must refuse to return an invalid schedule.
        real_certify = pipeline_module.certify

        def broken_certify(conflict, assignment, budget):
            result = real_certify(conflict, assignment, budget)
            return replace(result, assignment={node: 0 for node in result.assignment}, num_slots=1)

        with mock.patch.object(pipeline_module, "certify", broken_certify):
            with self.assertRaises(ScheduleValidationError):
                plan_schedule(grid_16())

if __name__ == "__main__":
    unittest.main()
