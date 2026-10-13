"""Part 2: generate a complete, runnable EMANE scenario from a schedule.

One scenario directory contains everything a single EMANE host needs:

    platform-01.xml ... platform-16.xml   one EMANE instance (NEM) per radio
    tdmanem.xml, tdmaradiomodel.xml,       radio definition: TDMA MAC + EMANE PHY
    transvirtual.xml                       virtual network interface per radio
    schedule.xml                           the TDMA schedule (emane_export.build_schedule_xml)
    scenario.json                          nodes, NEM ids, slots, links, pathloss and
                                           the packet-level PREDICTION for every link

Link model: EMANE's ``precomputed`` propagation model. Every link of G gets the
same pathloss; pairs outside radio range get no entry, so EMANE neither delivers
nor counts interference between them. This makes EMANE's notion of "who hears
whom" identical to G, so the experiment tests the schedule, not the radio physics.

The prediction rule, applied per directed link u -> v of G:

    delivered  iff  slot(v) != slot(u)                       (v is listening)
               and  no other w with slot(w) == slot(u)
                    and w adjacent to v                      (no collision at v)

A schedule that is a proper coloring of G^2 predicts 100% delivery on every
link. A schedule that only colors G predicts hidden-terminal losses.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import networkx as nx

from tdma_optimizer.coloring import Coloring, normalize_slots
from tdma_optimizer.emane_export import EmaneRadioParams, build_schedule_xml, nem_id_map
from tdma_optimizer.errors import InputValidationError
from tdma_optimizer.input_parser import check_node_count, load_coordinates_file
from tdma_optimizer.pipeline import PlanConfig, plan_schedule
from tdma_optimizer.topology import DEFAULT_RANGE_M, build_communication_graph

# One host, one container: OTA radio channel and event channel are multicast
# groups on the container's interface, looped back so co-located NEMs hear each other.
OTA_GROUP = "224.1.2.8:45702"
EVENT_GROUP = "224.1.2.8:45703"
DEFAULT_DEVICE = "eth0"
CONTROL_PORT_BASE = 47000
LINK_PATHLOSS_DB = 80.0  # 0 dBm tx -> -80 dBm rx, ~30 dB above the 1 MHz noise floor
PCR_URI = "file:///usr/share/emane/xml/models/mac/tdmaeventscheduler/tdmabasemodelpcr.xml"

# 11 Mbps: its PCR curve needs >= 5 dB SINR, so two equal-power transmitters
# colliding at a receiver (SINR ~ 0 dB) lose the frame, as in a real radio.
# At 1 Mbps the curve still decodes at 0 dB SINR, which would hide collisions.
EMANE_PARAMS = EmaneRadioParams(datarate="11M")


@dataclass(frozen=True)
class LinkOutcome:
    src: str
    dst: str
    delivered: bool
    reason: str  # "ok", "receiver transmitting", or "collision with <node>"


def predict_delivery(graph: nx.Graph, assignment: Mapping[str, int]) -> list[LinkOutcome]:
    """Expected outcome of a broadcast from every node to every one-hop neighbour."""
    outcomes = []
    for src in graph.nodes:
        for dst in graph.neighbors(src):
            if assignment[dst] == assignment[src]:
                outcomes.append(LinkOutcome(src, dst, False, "receiver transmitting"))
                continue
            rivals = [w for w in graph.neighbors(dst)
                      if w != src and assignment[w] == assignment[src]]
            if rivals:
                outcomes.append(LinkOutcome(src, dst, False, f"collision with {rivals[0]}"))
            else:
                outcomes.append(LinkOutcome(src, dst, True, "ok"))
    return outcomes


def g_only_coloring(graph: nx.Graph) -> Coloring:
    """Control schedule: DSATUR on G instead of G^2 (ignores hidden terminals on purpose)."""
    return normalize_slots(
        nx.coloring.greedy_color(graph, strategy="saturation_largest_first"), graph.nodes
    )


def _xml(root: ET.Element, doctype: str) -> str:
    ET.indent(root, space="  ")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<!DOCTYPE {doctype} SYSTEM "file:///usr/share/emane/dtd/{doctype}.dtd">\n'
            + ET.tostring(root, encoding="unicode") + "\n")


def _params(parent: ET.Element, values: Mapping[str, str]) -> None:
    for name, value in values.items():
        ET.SubElement(parent, "param", {"name": name, "value": value})


def platform_xml(nem: int, device: str) -> str:
    root = ET.Element("platform")
    _params(root, {
        "otamanagerchannelenable": "on",
        "otamanagerdevice": device,
        "otamanagergroup": OTA_GROUP,
        "otamanagerloopback": "on",
        "eventservicedevice": device,
        "eventservicegroup": EVENT_GROUP,
        "controlportendpoint": f"0.0.0.0:{CONTROL_PORT_BASE + nem}",
    })
    nem_el = ET.SubElement(root, "nem", {"id": str(nem), "definition": "tdmanem.xml"})
    transport = ET.SubElement(nem_el, "transport", {"definition": "transvirtual.xml"})
    _params(transport, {
        "device": f"emane{nem}",
        "address": f"10.100.0.{nem}",
        "mask": "255.255.255.0",
    })
    return _xml(root, "platform")


def nem_xml() -> str:
    root = ET.Element("nem")
    ET.SubElement(root, "transport", {"definition": "transvirtual.xml"})
    ET.SubElement(root, "mac", {"definition": "tdmaradiomodel.xml"})
    phy = ET.SubElement(root, "phy")
    _params(phy, {
        "fixedantennagain": "0.0",
        "fixedantennagainenable": "on",
        "bandwidth": EMANE_PARAMS.bandwidth,
        "noisemode": "all",
        "propagationmodel": "precomputed",
        "systemnoisefigure": "4.0",
        "subid": "7",
    })
    return _xml(root, "nem")


def mac_xml() -> str:
    root = ET.Element("mac", {"library": "tdmaeventschedulerradiomodel"})
    _params(root, {
        "fragmentcheckthreshold": "2",
        "fragmenttimeoutthreshold": "5",
        "neighbormetricdeletetime": "60.0",
        "neighbormetricupdateinterval": "1.0",
        "queue.aggregationenable": "on",
        "queue.aggregationslotthreshold": "90.0",
        "queue.depth": "255",
        "queue.fragmentationenable": "on",
        "queue.strictdequeueenable": "off",
        "pcrcurveuri": PCR_URI,
    })
    return _xml(root, "mac")


def transport_xml() -> str:
    root = ET.Element("transport", {"library": "transvirtual"})
    _params(root, {"bitrate": "0", "devicepath": "/dev/net/tun"})
    return _xml(root, "transport")


def write_scenario(
    out_dir: Path,
    label: str,
    graph: nx.Graph,
    assignment: Mapping[str, int],
    node_order: Sequence[str],
    device: str = DEFAULT_DEVICE,
    slot_us: int = EMANE_PARAMS.slot_duration_us,
) -> dict:
    """Write one runnable scenario directory and return its scenario.json content."""
    params = replace(EMANE_PARAMS, slot_duration_us=slot_us)
    out_dir.mkdir(parents=True, exist_ok=True)
    nems = nem_id_map(node_order)
    for node in node_order:
        (out_dir / f"platform-{nems[node]:02d}.xml").write_text(platform_xml(nems[node], device))
    (out_dir / "tdmanem.xml").write_text(nem_xml())
    (out_dir / "tdmaradiomodel.xml").write_text(mac_xml())
    (out_dir / "transvirtual.xml").write_text(transport_xml())
    (out_dir / "schedule.xml").write_text(build_schedule_xml(assignment, node_order, params))

    outcomes = predict_delivery(graph, assignment)
    scenario = {
        "label": label,
        "device": device,
        "event_group": EVENT_GROUP,
        "control_port_base": CONTROL_PORT_BASE,
        "slot_duration_us": params.slot_duration_us,
        "num_slots": max(assignment.values()) + 1,
        "datarate": EMANE_PARAMS.datarate,
        "link_pathloss_db": LINK_PATHLOSS_DB,
        "nodes": [
            {"name": n, "nem": nems[n], "slot": assignment[n], "pos": list(graph.nodes[n]["pos"])}
            for n in node_order
        ],
        "links": sorted([nems[u], nems[v]] for u, v in graph.edges),
        "expected": [
            {"src": nems[o.src], "dst": nems[o.dst], "delivered": o.delivered, "reason": o.reason}
            for o in outcomes
        ],
    }
    (out_dir / "scenario.json").write_text(json.dumps(scenario, indent=2))
    return scenario


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tdma-emane-scenario",
        description="Write EMANE scenarios for the optimized schedule and a G-only control.",
    )
    parser.add_argument("--input", required=True, metavar="FILE", help="JSON coordinates file")
    parser.add_argument("--out", required=True, metavar="DIR", help="output directory")
    parser.add_argument("--range", type=float, default=DEFAULT_RANGE_M, dest="radio_range")
    parser.add_argument("--expected-nodes", type=int, default=16)
    parser.add_argument("--slot-us", type=int, default=EMANE_PARAMS.slot_duration_us,
                        help="slot duration in microseconds (default 1000 = 1 ms)")
    parser.add_argument("--device", default=DEFAULT_DEVICE,
                        help="multicast interface inside the EMANE host (default eth0)")
    args = parser.parse_args(argv)

    try:
        coords = load_coordinates_file(args.input)
        check_node_count(coords, args.expected_nodes)
        plan = plan_schedule(coords, PlanConfig(radio_range=args.radio_range))
    except InputValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    graph = build_communication_graph(coords, args.radio_range)
    out = Path(args.out)
    runs = {
        "optimized": plan.assignment,
        "control-g-only": g_only_coloring(graph),
    }
    for label, assignment in runs.items():
        scenario = write_scenario(out / label, label, graph, assignment, plan.node_order, args.device,
                                  args.slot_us)
        lost = sum(1 for e in scenario["expected"] if not e["delivered"])
        print(f"{label:<16} {scenario['num_slots']} slots, {len(scenario['expected'])} directed links, "
              f"{lost} predicted losses -> {out / label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
