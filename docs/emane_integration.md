# Part 2: EMANE Integration Plan

**Status:** The schedule-to-XML bridge (`emane_export.py`, `--emane-xml`) is implemented and tested against the *documented* format. EMANE itself has **not** been installed or run as part of this submission. Everything below that depends on a live EMANE instance is a plan, and items still to confirm are marked **[confirm]**.

Primary references:

- EMANE TDMA model wiki: <https://github.com/adjacentlink/emane/wiki/TDMA-Model>
- emane-tutorial, Demonstration 8 (TDMA): <https://github.com/adjacentlink/emane-tutorial/wiki/Demonstration-8>
- Example schedule: `emane-tutorial/8/schedule.xml`

## 1. Roles: Brain and Engine

```
┌──────────────── Brain (this repo, Python) ─────────────┐        ┌──────── Engine (EMANE) ───────┐
│ coordinates → G → H=G² → coloring → validation         │        │ 16 NEMs, TDMA radio model     │
│      │                                  │              │  XML   │ (tdmaeventschedulerradiomodel)│
│      └── pathloss table from G          └── schedule ──┼──────▶ │ emaneevent-tdmaschedule       │
│                 │                                      │        │                               │
│                 └──────────────────────────────────────┼──────▶ │ pathloss events (link budget) │
│                                                        │        │                               │
│ verification ◀─── emanesh stats / packet captures ◀────┼─────── │ per-slot TX/RX status tables  │
└────────────────────────────────────────────────────────┘        └───────────────────────────────┘
```

EMANE emulates the MAC and PHY layers in real time: each **NEM** (Network Emulation Module) is one radio. Its TDMA model only transmits in the slots the schedule grants and computes reception, including interference, for every over-the-air frame. The Brain decides *who transmits when*. EMANE shows *what actually happens to packets* under that decision.

## 2. TDMA radio model essentials (from the documentation)

- MAC library: `tdmaeventschedulerradiomodel`, configured in a MAC XML (the tutorial's is `tdmaradiomodel.xml`, referenced by `tdmanem.xml`). The model has **no built-in schedule**: it waits for a TDMA Schedule event.
- **Structure:** a multiframe contains `frames`, each frame contains `slots` of `slotduration` µs (plus `slotoverhead`), on a transceiver `bandwidth`.
- **Full schedule** (contains `<structure>`): any slot not listed for a NEM becomes a **receive slot** for it; undefined frames are idle. Every NEM in the scenario must appear in a full schedule, because NEMs that are not referenced receive no event.
- **Update schedule** (no `<structure>`): modifies slots with no automatic filling.
- Delivery: `emaneevent-tdmaschedule schedule.xml -i <event-iface>`. Each NEM receives only its own part.
- A schedule takes effect at the next **multiframe boundary measured from the Unix epoch**, so all hosts must share synchronized clocks.

## 3. Mapping nodes to NEMs

`emane_export.nem_id_map()` assigns NEM IDs 1..N in the pipeline's natural node order: `Node_01 → NEM 1`, ..., `Node_16 → NEM 16`. The CLI prints this table with `--emane-xml`. The same mapping must be used when generating the platform files and the pathloss table. Treating the mapping as one shared artifact is the main defense against an off-by-one between the Brain and the Engine.

## 4. Schedule translation (implemented)

The Brain's assignment `{node: slot}` becomes one single-frame multiframe. Here is the real output for `grid_16` (`examples/grid_16_emane_schedule.xml`, abridged):

```xml
<emane-tdma-schedule>
  <structure frames="1" slots="9" slotoverhead="0" slotduration="1000" bandwidth="1M" />
  <multiframe frequency="2.4G" power="0" class="0" datarate="100M">
    <frame index="0">
      <slot index="0" nodes="1,4,13,16"><tx /></slot>   <!-- spatial reuse: 4 transmitters -->
      <slot index="1" nodes="2,14"><tx /></slot>
      ...
      <slot index="8" nodes="11"><tx /></slot>
    </frame>
  </multiframe>
</emane-tdma-schedule>
```

- `slots = K` (9). `slotduration = 1000` µs is the 1 ms slot requested, so the frame is K ms long.
- Each NEM is a transmitter in exactly one slot. Because this is a full schedule, it receives in the other K−1 slots.
- The tutorial's example writes `<slot .../>` with no child, while the wiki describes explicit `<tx/>`. The exporter emits the explicit `<tx/>` form. **[confirm]** which form the target EMANE version accepts, using `emanesh ... get table nems mac scheduler.ScheduleInfoTable`.
- Frequency, power, class and datarate are multiframe defaults from `EmaneRadioParams`. **[confirm]** datarate against slot size: at 1 ms, a 1 Mbps rate carries only ~125 bytes per slot, so fragmentation would dominate. The tutorial pairs a 1.5 ms slot with 100 Mbps. Choose so that one packet plus guard time fits in a slot.

## 5. Making EMANE's topology match the Brain's G

Scheduling is only meaningful if EMANE's notion of who hears whom matches G. Demonstration 8 uses `propagationmodel = precomputed`, where link quality comes from **pathloss events**. Plan:

1. From G, emit a pathloss table. For in-range pairs (d ≤ 500 m), use a pathloss giving a reliable SINR at the configured TX power. For out-of-range pairs, use a pathloss large enough to put the signal below the receiver's sensitivity, so the link is absent.
2. Publish the table with EMANE's pathloss event tool. **[confirm]** the exact `emaneevent-pathloss` arguments for the installed version.
3. Alternative: location events plus `freespace` or `2ray` propagation, with TX power and noise floor tuned so 500 m is the decode edge. This is more physical but harder to make match G exactly. Precomputed pathloss is preferred for a deterministic test.

Note that real interference reaches further than reliable decoding. With pathloss values derived purely from G, EMANE will reproduce the Brain's model rather than test it. A second experiment can add moderate pathloss between 2-hop and 3-hop pairs to probe how robust the two-hop rule is.

## 6. Timing, synchronization and frequency

| Parameter | Proposed | Notes |
|---|---|---|
| Slot duration | 1000 µs | Requested by the assessment |
| Slot overhead | 0 → tune | Guard time for propagation delay (500 m ≈ 1.7 µs, negligible) and clock skew |
| Frame | K slots = 9 ms for `grid_16` | Lower K means lower latency and a larger per-node share (1/K) |
| Multiframe | 1 frame | Multi-frame patterns would allow traffic weighting |
| Frequency | single 2.4 GHz | The Brain assumes one channel. Multi-frequency would turn this into a joint slot-channel problem |
| Clock sync | NTP/PTP across hosts; trivially shared on one host or container | Schedules activate on epoch-aligned multiframe boundaries |

On a single machine or a single Docker container, as the assessment allows, all NEMs share one clock, which removes the biggest source of TDMA error.

## 7. Packet-level validation plan

The goal is to show that EMANE *drops or permits packets strictly according to the schedule*.

1. **Bring-up.** Install EMANE (Adjacent Link packages, or one Docker image), with 16 NEMs using the virtual transport. Start the event service.
2. **Load the topology.** Publish pathloss events derived from G.
3. **Load the schedule.** Run `tdma-optimizer --input examples/grid_16.json --emane-xml schedule.xml`, then `emaneevent-tdmaschedule schedule.xml -i <iface>`. Verify with `emanesh <host> get table nems mac scheduler.ScheduleInfoTable scheduler.StructureInfoTable`.
4. **Offered load.** Every node broadcasts at a fixed rate (for example with MGEN or iperf in UDP broadcast mode). Capture with `tcpdump` on each node's virtual interface.
5. **Observe.** Read the per-NEM `TxSlotStatusTable` (Valid, Missed, Big) and `RxSlotStatusTable` (Valid, Missed, Idle, Tx, Long). Also check the PHY drop tables.
6. **Expected result with the Brain's schedule:** every node transmits only in its own slot, with no reception failures caused by overlapping transmissions. Each node delivers to all its 1-hop neighbors.
7. **Control experiment (key evidence).** Generate a schedule that colors **G instead of G²** (allowed by design: change one function). It assigns some 2-hop pairs, such as `Node_01`/`Node_03`, the same slot. Expected: `Node_02` shows collision-related reception failures in that slot. Comparing the two runs demonstrates that the distance-2 constraint is what prevents collisions.
8. **Automate the check.** A small script reads the `emanesh` tables or the pcap timestamps, maps each received frame to `(slot = floor((t mod frame) / slot_duration))`, and asserts that each frame's sender owns that slot.

## 8. Risks and open questions

- The XML format is followed exactly as documented, but has not been tested against a running EMANE. **[confirm]** on first bring-up.
- Exact parameter names differ between documentation pages (for example, the strict dequeue option). **[confirm]** against `emanesh <host> get config nems mac`.
- The tutorial environment is older Ubuntu with LXC. A modern Docker build may need adjustments.
- Pathloss-to-G calibration must hold for every pair, including 2-hop pairs that are just out of range.

## 9. Next steps (in order)

1. Build one Docker image with EMANE and the tutorial's TDMA configuration.
2. Reproduce Demonstration 8 unchanged, to confirm the environment works.
3. Swap in the generated `schedule.xml` and a 16-node platform.
4. Add the pathloss generator (`emane_export.build_pathloss_table`, roughly 30 lines, sharing `nem_id_map`).
5. Run the validation experiment and its G-only control, and record the tables.
