#!/usr/bin/env python3
"""Compare EMANE's measured packet delivery with the schedule's prediction, link by link.

Inputs (in each scenario directory): scenario.json (prediction), results.json
(frames sent / received per link) and emanesh/ (EMANE MAC statistics tables).

For every directed link of the communication graph the delivery ratio is
received / sent and classified as:
    DELIVERED  ratio >= 0.90
    BLOCKED    ratio <= 0.10
    PARTIAL    anything in between
A link MATCHES when the prediction says delivered and it is DELIVERED, or the
prediction says lost and it is BLOCKED.

EMANE's MAC drop tables split losses into causes:
    collision   frame overlapped another transmission at the receiver: the second
                frame is dropped as "Lock", the first fails its SINR check
    late        frame reached the receiver after its slot ended ("Slot Error":
                emulator timing, not the schedule)

Standard library only (Python 3.8+), so it runs on the host or in the container.

Usage:  python3 analyze.py SCENARIO_DIR [SCENARIO_DIR ...] [--markdown OUT.md]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DELIVERED, BLOCKED = 0.90, 0.10


def mac_drop_totals(scenario_dir: Path, frame_bytes: int) -> dict:
    """Frames dropped by EMANE's TDMA MAC, by cause, summed over all receivers.

    BroadcastByteDropTable0 counts bytes; every test frame is ``frame_bytes`` long,
    so bytes / frame_bytes is an exact frame count. RxSlotStatusTable counts frames.
    """
    totals = {"sinr": 0, "late": 0, "lock": 0, "rx_during_tx": 0}
    for path in sorted((scenario_dir / "emanesh").glob("nem-*-mac-tables.txt")):
        section, header = None, None
        for line in path.read_text().splitlines():
            if re.match(r"nem \d+\s+mac ", line):
                section, header = line.split()[-1], None
                continue
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if header is None:
                header = cells
                continue
            row = dict(zip(header, cells))
            if section == "BroadcastByteDropTable0":
                totals["sinr"] += int(row.get("SINR", 0)) // frame_bytes
                totals["late"] += int(row.get("Slot Error", 0)) // frame_bytes
            elif section == "RxSlotStatusTable":
                totals["lock"] += int(row.get("Lock", 0))
                totals["rx_during_tx"] += int(row.get("Tx", 0))
    totals["collisions"] = totals["sinr"] + totals["lock"]
    return totals


def analyse(scenario_dir: Path) -> dict:
    scenario = json.loads((scenario_dir / "scenario.json").read_text())
    results = json.loads((scenario_dir / "results.json").read_text())
    names = {n["nem"]: n["name"] for n in scenario["nodes"]}
    sent = {int(k): v for k, v in results["sent"].items()}
    received = results["received"]

    links = []
    for e in scenario["expected"]:
        src, dst = e["src"], e["dst"]
        got = received.get(f"{src}->{dst}", 0)
        ratio = got / sent[src] if sent[src] else 0.0
        measured = "DELIVERED" if ratio >= DELIVERED else "BLOCKED" if ratio <= BLOCKED else "PARTIAL"
        match = (e["delivered"] and measured == "DELIVERED") or (not e["delivered"] and measured == "BLOCKED")
        links.append({"src": names[src], "dst": names[dst], "predicted": e["delivered"],
                      "reason": e["reason"], "ratio": ratio, "measured": measured, "match": match})

    # Frames that crossed a pair that is NOT a link of G would mean EMANE's topology is wrong.
    expected_pairs = {f"{e['src']}->{e['dst']}" for e in scenario["expected"]}
    stray = {k: v for k, v in received.items() if k not in expected_pairs}

    return {
        "label": scenario["label"],
        "slots": scenario["num_slots"],
        "slot_us": scenario["slot_duration_us"],
        "links": links,
        "stray": stray,
        "frames_sent": sum(sent.values()),
        "realtime": results.get("realtime"),
        "mac": mac_drop_totals(scenario_dir, results.get("frame_bytes", 88)),
    }


def summary_lines(a: dict) -> list[str]:
    links = a["links"]
    pred_ok = [l for l in links if l["predicted"]]
    pred_lost = [l for l in links if not l["predicted"]]
    matches = sum(l["match"] for l in links)
    mean = lambda xs: 100 * sum(l["ratio"] for l in xs) / len(xs) if xs else 0.0
    return [
        f"Scenario            : {a['label']}  ({a['slots']} slots x {a['slot_us'] / 1000:g} ms)",
        f"Directed links      : {len(links)}  (predicted delivered {len(pred_ok)}, predicted lost {len(pred_lost)})",
        f"Mean delivery       : predicted-delivered links {mean(pred_ok):.1f}%, "
        f"predicted-lost links {mean(pred_lost):.1f}%",
        f"Prediction matches  : {matches}/{len(links)} links",
        f"Partial links       : {sum(l['measured'] == 'PARTIAL' for l in links)}",
        f"Frames on non-links : {sum(a['stray'].values())}",
        f"EMANE MAC drops     : collision {a['mac']['collisions']} frames "
        f"(overlap lock {a['mac']['lock']} + low SINR {a['mac']['sinr']}), "
        f"late (emulator timing) {a['mac']['late']}",
    ]


def markdown(analyses: list[dict]) -> str:
    out = ["| Scenario | Slots | Slot | Links | Predicted lost | Delivery on predicted-OK links "
           "| Delivery on predicted-lost links | Prediction matches | Collision drops (frames) | Late drops (frames) |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for a in analyses:
        links = a["links"]
        ok = [l for l in links if l["predicted"]]
        lost = [l for l in links if not l["predicted"]]
        pct = lambda xs: f"{100 * sum(l['ratio'] for l in xs) / len(xs):.1f}%" if xs else "none"
        out.append(f"| {a['label']} | {a['slots']} | {a['slot_us'] / 1000:g} ms | {len(links)} | {len(lost)} "
                   f"| {pct(ok)} | {pct(lost)} | {sum(l['match'] for l in links)}/{len(links)} "
                   f"| {a['mac']['collisions']} | {a['mac']['late']} |")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenario_dirs", nargs="+", type=Path)
    parser.add_argument("--markdown", type=Path, help="also write a markdown summary table here")
    parser.add_argument("--links", action="store_true", help="print every link")
    args = parser.parse_args()

    analyses = [analyse(d) for d in args.scenario_dirs]
    for a in analyses:
        print("=" * 78)
        print("\n".join(summary_lines(a)))
        shown = a["links"] if args.links else [l for l in a["links"] if not l["match"]][:15]
        if shown:
            print("  link                 predicted  measured   ratio  reason")
            for l in shown:
                print(f"  {l['src']}->{l['dst']:<10} {'ok' if l['predicted'] else 'lost':<10} "
                      f"{l['measured']:<10} {100 * l['ratio']:5.1f}%  {l['reason']}")
    print("=" * 78)
    if args.markdown:
        args.markdown.write_text(markdown(analyses))
        print(f"markdown summary written to {args.markdown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
