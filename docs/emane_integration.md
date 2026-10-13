# Part 2: EMANE Integration

**Status: implemented and measured.** The Python schedule drives a 16-radio EMANE 1.5.2 TDMA network in one Docker container. EMANE delivers or drops real packets exactly as the schedule predicts: **396 of 396** link-level predictions matched across two topologies and two schedules. The optimized schedule produced **zero collisions in every run.**

## 1. What EMANE is, in one paragraph

EMANE (Extendable Mobile Ad-hoc Network Emulator) emulates radios in real time. Each radio is an **NEM** (Network Emulation Module): one `emane` process with a virtual network interface (`emane1` … `emane16`), a MAC layer and a PHY layer. A packet written into `emane5` is queued by NEM 5's MAC and sent over an emulated radio channel. The other NEMs' PHYs decide whether they can hear it (pathloss, noise, interference), and their MACs decide whether to accept it. If accepted, it comes out of their own virtual interface. The **TDMA radio model** (`tdmaeventschedulerradiomodel`) only lets a radio transmit in the slots its schedule grants, and only receive in the others.

## 2. Architecture: Brain and Engine

```
 HOST (Python 3.11+, this package)                       DOCKER CONTAINER (EMANE 1.5.2)
 ┌───────────────────────────────────────┐               ┌──────────────────────────────────────────┐
 │ coordinates → G → H=G² → schedule     │               │ emane platform-01.xml … platform-16.xml  │
 │                                       │  scenario dir │   NEM n: emane<n> ─ TDMA MAC ─ PHY       │
 │ tdma-emane-scenario  ─────────────────┼──────────────▶│            ▲               │             │
 │   platform-NN.xml, tdmanem.xml,       │  (bind mount) │            │      OTA channel (multicast)│
 │   tdmaradiomodel.xml, schedule.xml,   │               │ run_experiment.py:                       │
 │   scenario.json (+ per-link PREDICTION)│              │   1 pathloss events  (links of G)        │
 │                                       │               │   2 TDMA schedule event (schedule.xml)   │
 │ analyze.py  ◀─────────────────────────┼───────────────│   3 raw Ethernet frames on every emane<n>│
 │   prediction vs measurement, per link │ results.json, │   4 emanesh: MAC/PHY statistics tables   │
 └───────────────────────────────────────┘ emanesh/*.txt └──────────────────────────────────────────┘
```

Only the container needs EMANE. The host side is ordinary Python and runs anywhere.

## 3. The integration bridge (what each file does)

| File | Runs on | Role |
|---|---|---|
| `src/tdma_optimizer/emane_export.py` | host | Schedule → EMANE TDMA schedule XML (`<structure>`, `<multiframe>`, one `<slot nodes=…><tx/>` per slot) |
| `src/tdma_optimizer/emane_scenario.py` (`tdma-emane-scenario`) | host | Writes a complete scenario: 16 platform files, NEM/MAC/transport definitions, the schedule, and `scenario.json` with the **predicted outcome of every link** |
| `emane/run_experiment.py` | container | Starts 16 NEMs, publishes pathloss + schedule events, sends traffic, records receptions, dumps EMANE statistics |
| `emane/analyze.py` | host or container | Compares measured delivery with the prediction, link by link, and splits EMANE's drops by cause |
| `emane/run_demo.sh` | host | All of the above in one command |
| `emane/Dockerfile` | build | EMANE 1.5.2 from official source (same recipe as the prebuilt image) |

## 4. Configuration choices and why

| Setting | Value | Why |
|---|---|---|
| Slot duration | **1000 µs** (1 ms), also run at 2 ms and 4 ms | 1 ms is the requirement. Longer slots separate schedule effects from emulator speed (§6) |
| Frame | 1 frame of K slots (9 for the grid) | One transmit slot per radio per frame, as computed by Part 1 |
| Schedule type | **Full schedule** (has `<structure>`) | EMANE makes every unlisted slot a receive slot, so each radio listens in the other K−1 slots |
| Frequency / bandwidth | 2.4 GHz / 1 MHz, one channel | The Brain assumes a single shared channel |
| Data rate | **11 Mbps** | An entry in EMANE's stock TDMA PCR curve. Its curve needs ≥ 5 dB SINR, so two equal-power transmitters colliding at a receiver (SINR ≈ 0 dB) lose the frame, like a real radio. At 1 Mbps the curve still decodes at 0 dB and would hide collisions |
| Propagation | **precomputed pathloss**, 80 dB on every link of G, no entry otherwise | Makes EMANE's "who hears whom" identical to G, so the experiment tests the schedule rather than radio physics. 0 dBm − 80 dB = −80 dBm, about 30 dB above the −110 dBm noise floor |
| OTA + event channels | multicast 224.1.2.8 on `eth0`, loopback on | All NEMs share one host |
| Real-time scheduling | `emane -r` when allowed; automatic fallback | Improves slot timing. Some container setups forbid it |

## 5. The experiment

For each topology, two schedules run through the same emulator:

1. **optimized**: Part 1's distance-2 coloring (9 slots for the grid).
2. **control-g-only**: DSATUR on **G only**, so neighbours differ but 2-hop pairs may share a slot (4 slots for the grid, the same shape as the assessment's 5-slot sample). It is deliberately wrong, to prove the emulator would catch a bad schedule.

Every radio broadcasts a numbered 88-byte Ethernet frame (EtherType 0x88B5) every 100 ms for 20 s (200 frames). Every radio counts the frames it receives, per sender.

**Prediction, per directed link u → v of G:** delivered if and only if v is not transmitting in u's slot, and no other neighbour of v transmits in u's slot. This is computed before the run and stored in `scenario.json`.

A link **matches** when predicted-delivered links measure ≥ 90% delivery and predicted-lost links measure ≤ 10%.

## 6. Results (measured)

All numbers come from `emane/results/*/summary.md`, produced by `emane/run_demo.sh` on a 2-vCPU cloud VM (EMANE 1.5.2, real-time scheduling on).

### 4×4 grid (the assessment's coordinates), 84 directed links

| Schedule | Slots | Slot | Delivery, predicted-OK links | Delivery, predicted-lost links | Prediction matches | Collision drops | Late drops |
|---|---|---|---|---|---|---|---|
| optimized | 9 | 1 ms | 79.7% | n/a | 34/84 | **0** | 3,408 |
| control-g-only | 4 | 1 ms | 31.5% | 16.6% | 28/84 | 2,059 | 11,363 |
| optimized | 9 | 2 ms | 98.7% | n/a | **84/84** | **0** | 221 |
| control-g-only | 4 | 2 ms | 96.5% | 2.9% | **84/84** | 11,994 | 578 |
| optimized | 9 | 4 ms | 99.7% | n/a | **84/84** | **0** | 45 |
| control-g-only | 4 | 4 ms | 99.8% | 1.1% | **84/84** | 12,629 | 35 |

### Field layout (2 components), 30 directed links

| Schedule | Slots | Slot | Delivery, predicted-OK links | Delivery, predicted-lost links | Prediction matches | Collision drops | Late drops |
|---|---|---|---|---|---|---|---|
| optimized | 4 | 1 ms | 41.4% | n/a | 0/30 | **0** | 3,514 |
| control-g-only | 3 | 1 ms | 32.7% | 5.9% | 16/30 | 207 | 4,848 |
| optimized | 4 | 4 ms | 99.7% | n/a | **30/30** | **0** | 17 |
| control-g-only | 3 | 4 ms | 100.0% | 1.2% | **30/30** | 3,746 | 11 |

"Collision drops" = frames EMANE's TDMA MAC discarded because they overlapped another transmission at the receiver (RX "Lock" + low-SINR drops). "Late drops" = frames that reached the receiver after their slot had ended (EMANE "Slot Error" / RX "Missed").

### What the results show

1. **EMANE enforces the schedule exactly.** At 2 ms and 4 ms, every one of 396 directed-link predictions (both schedules, both topologies) matched the measurement. No frame ever crossed a pair outside radio range.
2. **The distance-2 schedule is collision-free in practice, not just on paper.** The optimized schedule had 0 collision drops in all 5 runs, including at 1 ms.
3. **The control proves the 2-hop rule matters.** Coloring G alone lets hidden terminals share slots. EMANE then drops 97–99% of frames on exactly the 64 predicted links, for example `Node_01 → Node_02`, which collides with `Node_03` (also slot 0, also a neighbour of `Node_02`).
4. **At 1 ms, the bottleneck is the emulator host, not the schedule.** 16 real-time EMANE processes on 2 vCPUs could not process every frame within 1 ms, so EMANE marked frames "late". Evidence: late drops fall from 3,408 to 221 to 45 as the slot grows from 1 to 2 to 4 ms, while collisions stay at 0. The schedule logic does not change with slot length. A host with more cores should close the gap at 1 ms; this was not measured.

## 7. How to reproduce (Linux, including Arch)

```bash
# once: Docker
sudo pacman -S docker                      # Arch; Ubuntu: sudo apt install docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"            # then log out and back in
# once: this package
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# the demo: generate → emulate → compare (≈ 5 minutes)
emane/run_demo.sh                          # grid_16, 1 ms and 4 ms slots
emane/run_demo.sh examples/field_16.json
SLOTS_US="1000 2000 4000" emane/run_demo.sh
```

Results land in `emane/results/<topology>/`: `summary.txt`, `summary.md`, and per run `scenario.json`, `results.json`, `schedule.xml`, the platform XML files, and `emanesh/` tables.

Notes:

- The demo pulls the prebuilt image `lbitnetemu/emane:1.5.2` (built from the official v1.5.2 source on Ubuntu 22.04). To build it yourself instead: `docker build -t tdma-emane emane/` then `EMANE_IMAGE=tdma-emane emane/run_demo.sh`. That Dockerfile mirrors the image's published build steps but was not built in the author's environment.
- The container needs `--privileged` for `/dev/net/tun` and raw sockets. The script sets it.
- If the host forbids real-time scheduling in containers, the runner says so and continues without it, with more late drops at 1 ms. On cgroup-v1 hosts with RT group scheduling, `DOCKER_RT_FLAGS="--cpu-rt-runtime=850000"` grants it; the measurements above used this.

## 8. Inspecting EMANE directly

```bash
emanesh -p 47005 localhost get table nems mac RxSlotStatusTable       # per-slot RX: Valid, Missed, Lock, ...
emanesh -p 47005 localhost get table nems mac BroadcastByteDropTable0 # drops per sender: SINR, Slot Error, ...
emanesh -p 47005 localhost get table nems mac TxSlotStatusTable       # NEM 5 transmits only in its own slot
```

The same tables are saved in each run's `emanesh/` folder.

## 9. Limitations and next steps

- **1 ms fidelity depends on the host.** Next step: repeat at 1 ms on a machine with 8+ cores, or with fewer NEMs per host across several containers.
- **The link model is binary.** Every in-range link has the same pathloss. Next step: distance-based pathloss and a carrier-sense range larger than the communication range, to test how robust the 2-hop rule is.
- **Broadcast traffic only.** Unicast and routed traffic, for example over OLSR, are natural extensions.
- **Static schedule.** Mobility would use EMANE *update* schedules for only the radios whose slot changes.
