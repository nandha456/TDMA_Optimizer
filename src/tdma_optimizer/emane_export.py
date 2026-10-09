"""Part 2 bridge: convert a validated schedule into an EMANE TDMA schedule XML.

Format follows the EMANE TDMA model documentation
(https://github.com/adjacentlink/emane/wiki/TDMA-Model) and the emane-tutorial
demo 8 ``schedule.xml``::

    <emane-tdma-schedule>
      <structure frames="1" slots="K" slotoverhead="0" slotduration="1000" bandwidth="1M"/>
      <multiframe frequency="2.4G" power="0" class="0" datarate="100M">
        <frame index="0">
          <slot index="0" nodes="1,3"><tx/></slot>
          ...

Semantics relied on (from the wiki): this is a *full* schedule because it has a
``<structure>`` element; in a full schedule every slot a NEM is not listed in
becomes a receive slot for it. Each node is listed in exactly one slot, so each
radio transmits once per frame and listens in the other K-1 slots.

The file is delivered with ``emaneevent-tdmaschedule schedule.xml -i <iface>``.
This module only generates the XML; it does not need EMANE installed.
Generated output has been checked against the documented format, not yet
against a running EMANE instance (see docs/emane_integration.md).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from tdma_optimizer.errors import InputValidationError


@dataclass(frozen=True)
class EmaneRadioParams:
    slot_duration_us: int = 1000  # 1 ms slots, as requested in the assessment
    slot_overhead_us: int = 0
    bandwidth: str = "1M"
    frequency: str = "2.4G"
    datarate: str = "100M"
    power_dbm: float = 0
    traffic_class: int = 0


def nem_id_map(node_order: Sequence[str]) -> dict[str, int]:
    """Map node IDs to EMANE NEM IDs 1..N in the pipeline's natural node order."""
    return {node: index for index, node in enumerate(node_order, start=1)}


def build_schedule_xml(
    assignment: Mapping[str, int],
    node_order: Sequence[str],
    params: EmaneRadioParams = EmaneRadioParams(),
) -> str:
    """Return the full-schedule XML text for one single-frame multiframe."""
    if set(assignment) != set(node_order):
        raise InputValidationError("Assignment and node order must cover the same nodes.")
    if params.slot_duration_us <= 0 or params.slot_overhead_us < 0:
        raise InputValidationError("Slot duration must be positive and overhead non-negative.")

    nems = nem_id_map(node_order)
    num_slots = max(assignment.values(), default=-1) + 1

    root = ET.Element("emane-tdma-schedule")
    ET.SubElement(root, "structure", {
        "frames": "1",
        "slots": str(num_slots),
        "slotoverhead": str(params.slot_overhead_us),
        "slotduration": str(params.slot_duration_us),
        "bandwidth": params.bandwidth,
    })
    multiframe = ET.SubElement(root, "multiframe", {
        "frequency": params.frequency,
        "power": f"{params.power_dbm:g}",
        "class": str(params.traffic_class),
        "datarate": params.datarate,
    })
    frame = ET.SubElement(multiframe, "frame", {"index": "0"})
    for slot in range(num_slots):
        transmitters = [str(nems[n]) for n in node_order if assignment[n] == slot]
        slot_el = ET.SubElement(frame, "slot", {"index": str(slot), "nodes": ",".join(transmitters)})
        ET.SubElement(slot_el, "tx")

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def render_nem_table(node_order: Sequence[str]) -> str:
    """Node -> NEM ID table to accompany the XML (needed when building platform files)."""
    return "\n".join(f"  {node} -> NEM {nem}" for node, nem in nem_id_map(node_order).items())
