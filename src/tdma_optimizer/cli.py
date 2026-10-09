"""Command-line interface. Argument handling and exit codes only; logic lives in pipeline.py.

Exit status:
    0  schedule computed and verified
    2  usage or input error (argparse uses 2 as well)
    3  schedule failed verification (internal error; never reported as success)
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from tdma_optimizer import __version__
from tdma_optimizer.coloring import DEFAULT_RESTARTS, DEFAULT_SEED
from tdma_optimizer.emane_export import EmaneRadioParams, build_schedule_xml, render_nem_table
from tdma_optimizer.errors import InputValidationError, ScheduleValidationError
from tdma_optimizer.exact import DEFAULT_NODE_BUDGET
from tdma_optimizer.input_parser import check_node_count, load_coordinates_file, parse_coordinates
from tdma_optimizer.pipeline import PlanConfig, plan_schedule
from tdma_optimizer.report import render_report
from tdma_optimizer.topology import DEFAULT_RANGE_M

EXIT_OK = 0
EXIT_INPUT_ERROR = 2
EXIT_SCHEDULE_INVALID = 3

log = logging.getLogger("tdma_optimizer")


def _non_negative_int(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {value}")
    return value


def _positive_int(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError(f"must be > 0, got {value}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tdma-optimizer",
        description="Compute a collision-free TDMA slot schedule using distance-2 graph coloring.",
        epilog=(
            "examples:\n"
            "  tdma-optimizer --input examples/grid_16.json\n"
            "  tdma-optimizer --coordinates '{\"A\":[0,0],\"B\":[300,0],\"C\":[600,0]}' "
            "--expected-nodes 3"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", metavar="FILE", help="JSON file of {node_id: [x, y]}")
    source.add_argument("--coordinates", metavar="JSON", help="inline JSON string of {node_id: [x, y]}")
    parser.add_argument("--range", type=float, default=DEFAULT_RANGE_M, dest="radio_range", metavar="METERS",
                        help=f"radio range in meters, inclusive (default {DEFAULT_RANGE_M})")
    parser.add_argument("--expected-nodes", type=_positive_int, default=16, metavar="N",
                        help="required number of nodes (default 16)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, metavar="INT",
                        help=f"seed for randomized attempts (default {DEFAULT_SEED})")
    parser.add_argument("--restarts", type=_non_negative_int, default=DEFAULT_RESTARTS, metavar="N",
                        help=f"number of random-order greedy attempts (default {DEFAULT_RESTARTS})")
    parser.add_argument("--exact-budget", type=_non_negative_int, default=DEFAULT_NODE_BUDGET, metavar="N",
                        help="branch-and-bound node budget for proving optimality; 0 disables "
                             f"(default {DEFAULT_NODE_BUDGET})")
    parser.add_argument("--emane-xml", metavar="FILE",
                        help="also write the schedule as an EMANE TDMA schedule XML file")
    parser.add_argument("-v", "--verbose", action="store_true", help="log pipeline progress to stderr")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )

    try:
        coordinates = (
            load_coordinates_file(args.input) if args.input else parse_coordinates(args.coordinates)
        )
        check_node_count(coordinates, args.expected_nodes)
        log.info("parsed %d nodes", len(coordinates))
        config = PlanConfig(
            radio_range=args.radio_range,
            seed=args.seed,
            restarts=args.restarts,
            exact_budget=args.exact_budget,
        )
        plan = plan_schedule(coordinates, config)
    except InputValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except ScheduleValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        for detail in exc.errors:
            print(f"  - {detail}", file=sys.stderr)
        return EXIT_SCHEDULE_INVALID

    log.info("schedule: %d slots via %s", plan.num_slots, plan.method)
    print(render_report(plan))

    if args.emane_xml:
        xml_text = build_schedule_xml(plan.assignment, plan.node_order, EmaneRadioParams())
        try:
            Path(args.emane_xml).write_text(xml_text, encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot write {args.emane_xml}: {exc}", file=sys.stderr)
            return EXIT_INPUT_ERROR
        print(f"\nEMANE TDMA schedule written to {args.emane_xml}")
        print("NODE -> NEM MAPPING:")
        print(render_nem_table(plan.node_order))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
