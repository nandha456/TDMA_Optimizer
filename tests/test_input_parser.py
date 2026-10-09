import tempfile
import unittest
from pathlib import Path

from tdma_optimizer.errors import InputValidationError
from tdma_optimizer.input_parser import (
    check_node_count,
    load_coordinates_file,
    natural_key,
    parse_coordinates,
)


class ValidInput(unittest.TestCase):
    def test_parses_valid_json(self):
        coords = parse_coordinates('{"Node_01": [0.0, 0.0], "Node_02": [300, -12.5]}')
        self.assertEqual(coords, {"Node_01": (0.0, 0.0), "Node_02": (300.0, -12.5)})
        self.assertIsInstance(coords["Node_02"][0], float)

    def test_output_is_naturally_ordered(self):
        coords = parse_coordinates('{"N10": [0,0], "N2": [1,1], "N1": [2,2]}')
        self.assertEqual(list(coords), ["N1", "N2", "N10"])

    def test_natural_key(self):
        self.assertEqual(sorted(["Node_10", "Node_2", "Node_1"], key=natural_key),
                         ["Node_1", "Node_2", "Node_10"])

    def test_loads_example_file(self):
        coords = load_coordinates_file(Path(__file__).parent.parent / "examples" / "grid_16.json")
        self.assertEqual(len(coords), 16)


class InvalidInput(unittest.TestCase):
    def assertRejected(self, text: str, fragment: str) -> None:
        with self.assertRaises(InputValidationError) as ctx:
            parse_coordinates(text)
        self.assertIn(fragment.lower(), str(ctx.exception).lower())

    def test_malformed_json(self):
        self.assertRejected('{"Node_01": [0, 0]', "invalid json")

    def test_top_level_must_be_object(self):
        self.assertRejected("[[0, 0], [1, 1]]", "object")

    def test_empty_object(self):
        self.assertRejected("{}", "no nodes")

    def test_duplicate_node_ids(self):
        self.assertRejected('{"A": [0, 0], "A": [1, 1]}', "duplicate")

    def test_empty_and_whitespace_ids(self):
        self.assertRejected('{"": [0, 0]}', "non-empty")
        self.assertRejected('{" A": [0, 0]}', "whitespace")

    def test_wrong_dimension(self):
        self.assertRejected('{"A": [0]}', "exactly 2")
        self.assertRejected('{"A": [0, 0, 0]}', "exactly 2")

    def test_missing_coordinates(self):
        self.assertRejected('{"A": null}', "list")
        self.assertRejected('{"A": {"x": 0, "y": 0}}', "list")

    def test_string_coordinates(self):
        self.assertRejected('{"A": ["0", "0"]}', "must be a number")
        self.assertRejected('{"A": "0,0"}', "list")

    def test_boolean_coordinates(self):
        self.assertRejected('{"A": [true, 0]}', "must be a number")

    def test_non_finite(self):
        self.assertRejected('{"A": [NaN, 0]}', "non-finite")
        self.assertRejected('{"A": [0, Infinity]}', "non-finite")
        self.assertRejected('{"A": [-Infinity, 0]}', "non-finite")
        self.assertRejected('{"A": [1e999, 0]}', "finite")  # overflows to inf

    def test_non_string_input(self):
        with self.assertRaises(InputValidationError):
            parse_coordinates(None)  # type: ignore[arg-type]

    def test_missing_file(self):
        with self.assertRaises(InputValidationError):
            load_coordinates_file("/definitely/not/here.json")

    def test_file_with_bad_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("not json")
            with self.assertRaises(InputValidationError):
                load_coordinates_file(path)


class NodeCount(unittest.TestCase):
    def test_correct_count_passes(self):
        check_node_count({"A": (0.0, 0.0)}, 1)

    def test_incorrect_count_rejected_with_hint(self):
        with self.assertRaises(InputValidationError) as ctx:
            check_node_count({"A": (0.0, 0.0), "B": (1.0, 1.0)}, 16)
        self.assertIn("--expected-nodes 2", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
