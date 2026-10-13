#!/usr/bin/env python3
"""Run one EMANE scenario inside the EMANE container and record packet delivery.

Runs on the EMANE host (Ubuntu 22.04, Python 3.10, EMANE 1.5.x). Needs only the
standard library and EMANE's own Python package; it does NOT need tdma_optimizer.

Steps:
  1. start one ``emane`` process per radio (platform-NN.xml)
  2. publish pathloss events: one entry per link of G (precomputed propagation)
  3. publish the TDMA schedule with ``emaneevent-tdmaschedule``
  4. every radio broadcasts numbered Ethernet frames on its virtual interface;
     every radio counts which frames arrive, per sender
  5. dump EMANE's own MAC/PHY statistics tables with ``emanesh``
  6. write results.json next to scenario.json

Usage:  python3 run_experiment.py SCENARIO_DIR [--duration SECONDS] [--interval SECONDS]
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

from emane.events import EventService, PathlossEvent

ETHERTYPE = 0x88B5  # IEEE "local experimental" EtherType: our test frames, nothing else
MAGIC = b"TDMA"
FRAME = struct.Struct("!4sHI")  # magic, source NEM, sequence number
PADDING = 64
FRAME_BYTES = 14 + FRAME.size + PADDING  # Ethernet header + payload = 88 bytes on the wire


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def realtime_available() -> bool:
    """EMANE's -r flag needs SCHED_FIFO; some container setups forbid it."""
    return subprocess.run(["chrt", "-f", "1", "true"], capture_output=True).returncode == 0


def start_emane(scenario_dir: Path, nems: list[int], realtime: bool) -> list[subprocess.Popen]:
    procs = []
    flags = ["-r"] if realtime else []
    for nem in nems:
        procs.append(subprocess.Popen(
            ["emane", f"platform-{nem:02d}.xml", *flags, "-l", "2", "-f", f"emane-{nem:02d}.log"],
            cwd=scenario_dir, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        ))
    deadline = time.time() + 30
    while time.time() < deadline:
        if all(Path(f"/sys/class/net/emane{n}").exists() for n in nems):
            time.sleep(1.0)
            dead = [n for n, p in zip(nems, procs) if p.poll() is not None]
            if dead:
                raise RuntimeError(f"emane exited for NEM(s) {dead}; see emane-NN.log")
            return procs
        time.sleep(0.2)
    raise RuntimeError("virtual interfaces did not appear within 30 s; see emane-NN.log")


def publish_pathloss(scenario: dict) -> None:
    group, port = scenario["event_group"].split(":")
    service = EventService((group, int(port), scenario["device"]))
    neighbours: dict[int, set[int]] = {n["nem"]: set() for n in scenario["nodes"]}
    for a, b in scenario["links"]:
        neighbours[a].add(b)
        neighbours[b].add(a)
    for target, sources in neighbours.items():
        event = PathlossEvent()
        for src in sorted(sources):
            event.append(src, forward=scenario["link_pathloss_db"])
        service.publish(target, event)


def publish_schedule(scenario_dir: Path, device: str) -> None:
    subprocess.run(["emaneevent-tdmaschedule", "schedule.xml", "-i", device],
                   cwd=scenario_dir, check=True)


def mac_address(device: str) -> bytes:
    text = Path(f"/sys/class/net/{device}/address").read_text().strip()
    return bytes(int(part, 16) for part in text.split(":"))


def receiver(device: str, nem: int, counts: dict, stop: threading.Event) -> None:
    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETHERTYPE))
    sock.bind((device, ETHERTYPE))
    sock.settimeout(0.2)
    while not stop.is_set():
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue
        if addr[2] == socket.PACKET_OUTGOING or len(data) < 14 + FRAME.size:
            continue
        magic, src, _seq = FRAME.unpack_from(data, 14)
        if magic == MAGIC and src != nem:
            key = f"{src}->{nem}"
            counts[key] = counts.get(key, 0) + 1
    sock.close()


def run_traffic(nems: list[int], duration: float, interval: float) -> tuple[dict, dict]:
    counts: dict[str, int] = {}
    sent: dict[int, int] = {n: 0 for n in nems}
    stop = threading.Event()
    threads = [threading.Thread(target=receiver, args=(f"emane{n}", n, counts, stop), daemon=True)
               for n in nems]
    for t in threads:
        t.start()
    time.sleep(0.5)

    senders = {}
    for n in nems:
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
        sock.bind((f"emane{n}", 0))
        senders[n] = (sock, mac_address(f"emane{n}"))

    rounds = int(duration / interval)
    for seq in range(rounds):
        start = time.time()
        for n in nems:
            sock, mac = senders[n]
            header = b"\xff" * 6 + mac + struct.pack("!H", ETHERTYPE)
            sock.send(header + FRAME.pack(MAGIC, n, seq) + b"\x00" * PADDING)
            sent[n] += 1
        time.sleep(max(0.0, interval - (time.time() - start)))

    time.sleep(2.0)  # let the last frames drain through their slots
    stop.set()
    for t in threads:
        t.join()
    for sock, _ in senders.values():
        sock.close()
    return sent, counts


def dump_tables(scenario_dir: Path, scenario: dict) -> None:
    out = scenario_dir / "emanesh"
    out.mkdir(exist_ok=True)
    for node in scenario["nodes"]:
        nem = node["nem"]
        port = str(scenario["control_port_base"] + nem)
        commands = {
            "mac-tables": ["get", "table", "nems", "mac"],
            "phy-tables": ["get", "table", "nems", "phy",
                           "BroadcastPacketAcceptTable0", "BroadcastPacketDropTable0"],
        }
        for name, cmd in commands.items():
            result = subprocess.run(["emanesh", "-p", port, "localhost", *cmd],
                                    capture_output=True, text=True, timeout=30)
            (out / f"nem-{nem:02d}-{name}.txt").write_text(result.stdout + result.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenario_dir", type=Path)
    parser.add_argument("--duration", type=float, default=20.0, help="seconds of traffic")
    parser.add_argument("--interval", type=float, default=0.1, help="seconds between frames per radio")
    args = parser.parse_args()

    scenario_dir = args.scenario_dir.resolve()
    scenario = json.loads((scenario_dir / "scenario.json").read_text())
    nems = [n["nem"] for n in scenario["nodes"]]
    log(f"scenario '{scenario['label']}': {len(nems)} radios, {scenario['num_slots']} slots "
        f"of {scenario['slot_duration_us']} us at {scenario['datarate']}bps")

    for stale in ["results.json", *(p.name for p in scenario_dir.glob("emane-*.log"))]:
        (scenario_dir / stale).unlink(missing_ok=True)
    realtime = realtime_available()
    if not realtime:
        log("WARNING: realtime scheduling not permitted; running EMANE without -r "
            "(expect more late-slot drops at 1 ms)")
    procs = start_emane(scenario_dir, nems, realtime)
    try:
        log("emane running; publishing pathloss for the communication graph")
        publish_pathloss(scenario)
        log("publishing TDMA schedule")
        publish_schedule(scenario_dir, scenario["device"])
        time.sleep(3.0)  # schedule activates on the next multiframe boundary
        log(f"sending traffic for {args.duration:.0f} s")
        sent, counts = run_traffic(nems, args.duration, args.interval)
        log("collecting EMANE statistics tables")
        dump_tables(scenario_dir, scenario)
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()

    results = {"label": scenario["label"], "duration_s": args.duration,
               "interval_s": args.interval, "frame_bytes": FRAME_BYTES, "realtime": realtime,
               "sent": sent, "received": counts}
    (scenario_dir / "results.json").write_text(json.dumps(results, indent=2))
    log(f"done: {sum(sent.values())} frames sent, {sum(counts.values())} receptions recorded")
    return 0


if __name__ == "__main__":
    if os.geteuid() != 0:
        sys.exit("run as root inside the EMANE container (needs /dev/net/tun and raw sockets)")
    sys.exit(main())
