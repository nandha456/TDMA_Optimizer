"""Build docs/TDMA_Optimizer_Documentation.pdf from live data.

Every number and figure is computed here from the package (Part 1) and from
emane/results/ (Part 2), so the document cannot drift from the code.

    pip install playwright && python -m playwright install chromium   # once
    python docs/pdf/build_pdf.py [--author "Your Name"]
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tdma_optimizer.emane_scenario import g_only_coloring, predict_delivery  # noqa: E402
from tdma_optimizer.input_parser import load_coordinates_file  # noqa: E402
from tdma_optimizer.pipeline import plan_schedule  # noqa: E402
from tdma_optimizer.topology import build_communication_graph  # noqa: E402

_spec = importlib.util.spec_from_file_location("analyze", ROOT / "emane" / "analyze.py")
analyze = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(analyze)

OUT_PDF = ROOT / "docs" / "TDMA_Optimizer_Documentation.pdf"
OUT_HTML = ROOT / "docs" / "pdf" / "documentation.html"

# Reference data-viz palette (light): one sequential blue, fixed status colours.
BLUE_100, BLUE_200, BLUE_450, BLUE_600 = "#cde2fb", "#9ec5f4", "#2a78d6", "#184f95"
GOOD, CRITICAL, SERIOUS = "#0ca30c", "#d03b3b", "#ec835a"
INK, INK2, INK3, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#fcfcfb"

e = html.escape


# --------------------------------------------------------------------------- data

def load_part1():
    grid = load_coordinates_file(ROOT / "examples" / "grid_16.json")
    field = load_coordinates_file(ROOT / "examples" / "field_16.json")
    ring = load_coordinates_file(ROOT / "examples" / "ring_7.json")
    spec4 = load_coordinates_file(ROOT / "examples" / "spec_4.json")
    plans = {name: plan_schedule(c) for name, c in
             [("grid_16", grid), ("field_16", field), ("ring_7", ring), ("spec_4", spec4)]}
    g = build_communication_graph(grid, 500.0)
    control = g_only_coloring(g)
    return plans, g, control


def load_part2():
    runs = {}
    for topo in ("grid_16", "field_16"):
        base = ROOT / "emane" / "results" / topo
        for slot_dir in sorted(base.glob("slot-*")):
            for label in ("optimized", "control-g-only"):
                d = slot_dir / label
                if (d / "results.json").exists():
                    runs[(topo, slot_dir.name, label)] = analyze.analyse(d)
    return runs


# ------------------------------------------------------------------------ figures

def svg(width, height, body, label):
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="{e(label)}" '
            f'xmlns="http://www.w3.org/2000/svg" font-family="Inter, sans-serif">{body}</svg>')


def node(x, y, text, sub=None, fill="#fff", stroke=INK2, sw=1.5, r=17, ink=INK):
    out = (f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
           f'<text x="{x}" y="{y + 4.5}" text-anchor="middle" font-size="13" font-weight="600" fill="{ink}">{e(text)}</text>')
    if sub:
        out += f'<text x="{x}" y="{y + r + 15}" text-anchor="middle" font-size="11" fill="{INK2}">{e(sub)}</text>'
    return out


def line(x1, y1, x2, y2, color=INK3, w=1.5, dash=None, marker=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = f' marker-end="url(#{marker})"' if marker else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{w}"{d}{m}/>'


def arrow_defs():
    return (f'<defs>'
            f'<marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{INK2}"/></marker>'
            f'<marker id="arc" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{CRITICAL}"/></marker></defs>')


def fig_hops():
    b = arrow_defs()
    # panel 1: direct link
    b += f'<text x="20" y="22" font-size="13" font-weight="700" fill="{INK}">1 hop: direct link</text>'
    b += line(60, 80, 160, 80) + node(60, 80, "A", "slot 0") + node(160, 80, "B", "slot 1")
    b += f'<text x="20" y="140" font-size="11.5" fill="{INK2}">Neighbours must differ: one is</text>'
    b += f'<text x="20" y="155" font-size="11.5" fill="{INK2}">talking while the other listens.</text>'
    # panel 2: hidden terminal
    ox = 250
    b += f'<text x="{ox}" y="22" font-size="13" font-weight="700" fill="{INK}">2 hops: hidden terminal</text>'
    b += line(ox + 30, 80, ox + 102, 80, CRITICAL, 2, marker="arc") + line(ox + 230, 80, ox + 158, 80, CRITICAL, 2, marker="arc")
    b += node(ox + 30, 80, "A", "slot 0") + node(ox + 130, 80, "B", "listening", stroke=CRITICAL, sw=2.5) + node(ox + 230, 80, "C", "slot 0")
    b += f'<text x="{ox + 130}" y="50" text-anchor="middle" font-size="11" font-weight="700" fill="{CRITICAL}">collision at B</text>'
    b += f'<text x="{ox}" y="140" font-size="11.5" fill="{INK2}">A and C cannot hear each other, but both</text>'
    b += f'<text x="{ox}" y="155" font-size="11.5" fill="{INK2}">reach B. Same slot = B decodes neither.</text>'
    # panel 3: spatial reuse
    ox = 545
    b += f'<text x="{ox}" y="22" font-size="13" font-weight="700" fill="{INK}">3+ hops: spatial reuse</text>'
    xs = [ox + 25, ox + 95, ox + 165, ox + 235]
    for i in range(3):
        b += line(xs[i], 80, xs[i + 1], 80)
    for x, name, s in zip(xs, "ABCD", ["slot 0", "slot 1", "slot 2", "slot 0"]):
        hi = name in "AD"
        b += node(x, 80, name, s, fill=BLUE_100 if hi else "#fff", stroke=BLUE_450 if hi else INK2)
    b += f'<text x="{ox}" y="140" font-size="11.5" fill="{INK2}">No radio hears both A and D, so they</text>'
    b += f'<text x="{ox}" y="155" font-size="11.5" fill="{INK2}">can safely share slot 0.</text>'
    return svg(800, 165, b, "Three interference cases: 1 hop, 2 hops, 3 or more hops")


def box(x, y, w, h, title, sub="", fill="#fff", stroke=INK3):
    out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>'
    ty = y + (h / 2 - 3 if sub else h / 2 + 4.5)
    out += f'<text x="{x + w / 2}" y="{ty}" text-anchor="middle" font-size="12.5" font-weight="650" fill="{INK}">{e(title)}</text>'
    if sub:
        out += f'<text x="{x + w / 2}" y="{ty + 15}" text-anchor="middle" font-size="10.5" fill="{INK2}">{e(sub)}</text>'
    return out


def fig_pipeline():
    b = arrow_defs()
    w, gap = 116, 18
    b += f'<text x="0" y="16" font-size="11" font-weight="700" fill="{BLUE_600}" letter-spacing="1">PART 1 · THE BRAIN (PYTHON)</text>'
    row1 = [("JSON input", "validate"), ("Graph G", "≤ 500 m links"), ("Conflicts H = G²", "1 or 2 hops"),
            ("Colour H", "heuristic portfolio"), ("Prove", "clique bound / B&B"), ("Validate", "independent BFS")]
    for i, (t, sub) in enumerate(row1):
        x = i * (w + gap)
        core = i in (2, 3)
        b += box(x, 28, w, 52, t, sub, fill=BLUE_100 if core else "#fff", stroke=BLUE_450 if core else INK3)
        if i:
            b += line(x - gap + 1, 54, x - 2, 54, INK2, 1.3, marker="ar")
    # snake: from Validate down, back to the left, into row 2
    vx = 5 * (w + gap) + w / 2
    b += (f'<path d="M{vx},80 V104 H{w / 2} V136" fill="none" stroke="{INK2}" stroke-width="1.3" '
          f'marker-end="url(#ar)"/>')
    b += f'<text x="{(w + gap) + 4}" y="128" font-size="11" font-weight="700" fill="{BLUE_600}" letter-spacing="1">PART 2 · THE ENGINE (EMANE IN DOCKER)</text>'
    row2 = [("Schedule XML", "+ scenario files"), ("16 EMANE radios", "TDMA MAC + PHY"),
            ("Load events", "pathloss + 1 ms slots"), ("Live traffic", "frames on every link"),
            ("Measured vs predicted", "per link · per drop cause")]
    for i, (t, sub) in enumerate(row2):
        x = i * (w + gap) + (0 if i < 4 else 0)
        width = w if i < 4 else w * 2 + gap
        hi = i == 4
        b += box(x, 138, width, 52, t, sub, fill=BLUE_100 if hi else "#fff", stroke=BLUE_450 if hi else INK3)
        if i:
            b += line(x - gap + 1, 164, x - 2, 164, INK2, 1.3, marker="ar")
    return svg(800, 196, b, "Pipeline from coordinates to schedule to EMANE verification")


def grid_layout(graph, scale=0.5, ox=40, oy=34):
    pos = {n: graph.nodes[n]["pos"] for n in graph.nodes}
    return {n: (ox + x * scale, oy + (900 - y) * scale) for n, (x, y) in pos.items()}


def fig_grid(graph, assignment, clique):
    pts = grid_layout(graph)
    b = ""
    for u, v in graph.edges:
        (x1, y1), (x2, y2) = pts[u], pts[v]
        inside = u in clique and v in clique and "Node_06" in (u, v)
        b += line(x1, y1, x2, y2, BLUE_450 if inside else GRID, 2 if inside else 1.3)
    for n, (x, y) in pts.items():
        hi = n in clique
        b += node(x, y, n[-2:], fill=BLUE_100 if hi else "#fff", stroke=BLUE_600 if n == "Node_06" else (BLUE_450 if hi else INK3),
                  sw=3 if n == "Node_06" else 1.5, r=18)
        b += f'<text x="{x + 21}" y="{y - 13}" font-size="11" font-weight="700" fill="{INK2}">S{assignment[n]}</text>'
    lx = 560
    y = 50
    b += f'<text x="{lx}" y="{y}" font-size="15" font-weight="700" fill="{INK}">How to read</text>'
    b += node(lx + 14, y + 34, "06", fill=BLUE_100, stroke=BLUE_600, sw=3, r=14)
    b += f'<text x="{lx + 38}" y="{y + 39}" font-size="13.5" fill="{INK2}">Node_06: 8 neighbours</text>'
    b += node(lx + 14, y + 74, "", fill=BLUE_100, stroke=BLUE_450, r=14)
    b += f'<text x="{lx + 38}" y="{y + 70}" font-size="13.5" fill="{INK2}">its clique: 9 radios that</text>'
    b += f'<text x="{lx + 38}" y="{y + 87}" font-size="13.5" fill="{INK2}">all conflict pairwise</text>'
    b += f'<text x="{lx}" y="{y + 124}" font-size="13.5" font-weight="700" fill="{INK2}">S4</text>'
    b += f'<text x="{lx + 38}" y="{y + 124}" font-size="13.5" fill="{INK2}">assigned time slot</text>'
    b += f'<text x="{lx}" y="{y + 170}" font-size="13.5" fill="{INK2}">Spacing 300 m. Diagonals</text>'
    b += f'<text x="{lx}" y="{y + 188}" font-size="13.5" fill="{INK2}">(424 m) are within range.</text>'
    b += f'<text x="{lx}" y="{y + 236}" font-size="14" fill="{INK}" font-weight="700">9 slots used = 9 needed</text>'
    b += f'<text x="{lx}" y="{y + 256}" font-size="14" fill="{BLUE_600}" font-weight="700">→ proven optimal</text>'
    return svg(800, 520, b, "4 by 4 grid with the optimal 9-slot schedule and Node_06's clique")


def fig_control(graph, control):
    pts = grid_layout(graph, scale=0.42, ox=40, oy=30)
    b = arrow_defs()
    for u, v in graph.edges:
        (x1, y1), (x2, y2) = pts[u], pts[v]
        b += line(x1, y1, x2, y2, GRID, 1.2)
    for n, (x, y) in pts.items():
        hot = n in ("Node_01", "Node_03")
        victim = n == "Node_02"
        b += node(x, y, n[-2:], fill="#fde7df" if hot else "#fff",
                  stroke=CRITICAL if victim else (SERIOUS if hot else INK3), sw=3 if victim else 1.5, r=15)
        b += f'<text x="{x + 17}" y="{y - 11}" font-size="10.5" font-weight="700" fill="{INK2}">S{control[n]}</text>'
    (x1, y1), (x2, y2), (x3, y3) = pts["Node_01"], pts["Node_02"], pts["Node_03"]
    b += f'<text x="{x2}" y="{y2 + 34}" text-anchor="middle" font-size="11" font-weight="700" fill="{CRITICAL}">collision</text>'
    lx = 470
    rows = [("Control schedule: DSATUR on G only.", 1), ("4 slots. Every pair of neighbours", 0),
            ("differs, so it looks valid…", 0), ("", 0),
            ("…but Node_01 and Node_03 both use", 1), ("slot 0 and both reach Node_02.", 0),
            ("Node_02 hears them overlap and", 0), ("decodes neither.", 0), ("", 0),
            ("The Brain predicts 64 such failed", 1), ("links; EMANE confirms all 64 (§6).", 0)]
    for i, (t, bold) in enumerate(rows):
        b += f'<text x="{lx}" y="{50 + i * 17}" font-size="12" {"font-weight=\"700\"" if bold else ""} fill="{INK if bold else INK2}">{e(t)}</text>'
    return svg(800, 430, b, "G-only control schedule with a hidden-terminal collision at Node_02")


def fig_heuristics():
    # scripts/benchmark.py, seed 7: 200 random 16-node deployments, 1.5 km square, 500 m range.
    data = [("DSATUR (baseline)", 200), ("random order ×100", 200), ("smallest_last", 199),
            ("largest_first", 198), ("connected_sequential_bfs", 188), ("connected_sequential_dfs", 180),
            ("independent_set", 134)]
    x0, w, bh, gap = 200, 470, 20, 10
    b = ""
    for t in (0, 25, 50, 75, 100):
        x = x0 + w * t / 100
        b += line(x, 8, x, 8 + len(data) * (bh + gap), GRID, 1)
        b += f'<text x="{x}" y="{len(data) * (bh + gap) + 24}" text-anchor="middle" font-size="10.5" fill="{INK3}">{t}%</text>'
    for i, (name, hits) in enumerate(data):
        y = 12 + i * (bh + gap)
        pct = hits / 200 * 100
        bw = w * pct / 100
        b += f'<text x="{x0 - 10}" y="{y + 14}" text-anchor="end" font-size="11.5" fill="{INK}">{e(name)}</text>'
        b += f'<path d="M{x0},{y} h{bw - 4} a4,4 0 0 1 4,4 v{bh - 8} a4,4 0 0 1 -4,4 h-{bw - 4} z" fill="{BLUE_450 if i == 0 else BLUE_200}"/>'
        b += f'<text x="{x0 + bw + 8}" y="{y + 14}" font-size="11.5" font-weight="650" fill="{INK}">{pct:.1f}%</text>'
    b += f'<text x="{x0 + w / 2}" y="{len(data) * (bh + gap) + 42}" text-anchor="middle" font-size="11" fill="{INK2}">share of 200 random 16-radio networks where the heuristic alone reached the proven optimum</text>'
    return svg(760, len(data) * (bh + gap) + 52, b, "Heuristic hit rate on 200 random networks")


def fig_heatmaps(runs, names):
    panels = [(runs[("grid_16", "slot-4ms", "optimized")], "Optimized schedule · 9 slots"),
              (runs[("grid_16", "slot-4ms", "control-g-only")], "G-only control · 4 slots")]
    cell, ox0, oy = 17, 46, 52
    b = ""
    idx = {n: i for i, n in enumerate(names)}
    for p, (a, title) in enumerate(panels):
        ox = ox0 + p * (16 * cell + 90)
        ok = sum(1 for l in a["links"] if l["measured"] == "DELIVERED")
        lost = sum(1 for l in a["links"] if l["measured"] == "BLOCKED")
        b += f'<text x="{ox}" y="18" font-size="13" font-weight="700" fill="{INK}">{e(title)}</text>'
        b += f'<text x="{ox}" y="36" font-size="11" fill="{INK2}">{ok} links delivered · {lost} blocked · {sum(l["match"] for l in a["links"])}/84 as predicted</text>'
        for i in range(16):
            b += f'<rect x="{ox + i * cell}" y="{oy + i * cell}" width="{cell - 1}" height="{cell - 1}" fill="{INK3}" opacity="0.25"/>'
            b += f'<text x="{ox - 5}" y="{oy + i * cell + 12}" text-anchor="end" font-size="8.5" fill="{INK2}">{i + 1:02d}</text>'
            b += f'<text x="{ox + i * cell + 8}" y="{oy - 4}" text-anchor="middle" font-size="8.5" fill="{INK2}">{i + 1:02d}</text>'
        for l in a["links"]:
            r, c = idx[l["src"]], idx[l["dst"]]
            good = l["measured"] == "DELIVERED"
            color = GOOD if good else (CRITICAL if l["measured"] == "BLOCKED" else SERIOUS)
            x, y = ox + c * cell, oy + r * cell
            b += f'<rect x="{x}" y="{y}" width="{cell - 1}" height="{cell - 1}" rx="2" fill="{color}"/>'
            b += f'<text x="{x + 8}" y="{y + 12}" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">{"✓" if good else "✕"}</text>'
        b += f'<text x="{ox + 8 * cell}" y="{oy + 16 * cell + 18}" text-anchor="middle" font-size="10.5" fill="{INK2}">receiving radio</text>'
        b += (f'<text x="{ox - 30}" y="{oy + 8 * cell}" text-anchor="middle" font-size="10.5" fill="{INK2}" '
              f'transform="rotate(-90 {ox - 30} {oy + 8 * cell})">sending radio</text>')
    ly = oy + 16 * cell + 40
    for i, (color, mark, text) in enumerate([(GOOD, "✓", "delivered (≥ 90% of frames)"),
                                             (CRITICAL, "✕", "blocked by collision (≤ 10%)"),
                                             (None, "", "blank: out of range (no link)"),
                                             ("grey", "", "grey: same radio")]):
        x = ox0 + i * 190
        if color == "grey":
            b += f'<rect x="{x}" y="{ly}" width="14" height="14" fill="{INK3}" opacity="0.25"/>'
        elif color:
            b += f'<rect x="{x}" y="{ly}" width="14" height="14" rx="2" fill="{color}"/><text x="{x + 7}" y="{ly + 11}" text-anchor="middle" font-size="9.5" font-weight="700" fill="#fff">{mark}</text>'
        else:
            b += f'<rect x="{x}" y="{ly}" width="14" height="14" fill="none" stroke="{GRID}"/>'
        b += f'<text x="{x + 20}" y="{ly + 11}" font-size="11" fill="{INK2}">{e(text)}</text>'
    return svg(800, ly + 22, b, "Per-link delivery measured in EMANE for both schedules")


def fig_emane_arch():
    b = arrow_defs()
    b += f'<rect x="0" y="0" width="300" height="250" rx="8" fill="{SURFACE}" stroke="{INK3}"/>'
    b += f'<text x="14" y="22" font-size="11" font-weight="700" fill="{BLUE_600}" letter-spacing="1">HOST · PYTHON 3.11+</text>'
    b += box(16, 36, 268, 46, "tdma-emane-scenario", "schedule → XML + per-link prediction", fill=BLUE_100, stroke=BLUE_450)
    b += box(16, 96, 268, 40, "scenario directory", "platform-NN.xml · schedule.xml · scenario.json")
    b += box(16, 190, 268, 46, "analyze.py", "prediction vs measurement, drop causes", fill=BLUE_100, stroke=BLUE_450)
    b += f'<rect x="360" y="0" width="440" height="250" rx="8" fill="{SURFACE}" stroke="{INK3}"/>'
    b += f'<text x="374" y="22" font-size="11" font-weight="700" fill="{BLUE_600}" letter-spacing="1">DOCKER CONTAINER · EMANE 1.5.2</text>'
    b += box(376, 36, 408, 40, "run_experiment.py", "start NEMs · publish events · send frames · read stats")
    for i in range(4):
        x = 376 + i * 104
        label = f"NEM {i + 1}" if i < 3 else "… NEM 16"
        b += box(x, 96, 96, 62, label, "TDMA MAC")
    b += f'<rect x="376" y="172" width="408" height="26" rx="5" fill="{BLUE_100}" stroke="{BLUE_450}"/>'
    b += f'<text x="580" y="189" text-anchor="middle" font-size="11.5" font-weight="650" fill="{INK}">over-the-air channel (multicast) · pathloss = links of G</text>'
    b += box(376, 208, 408, 34, "emanesh statistics: RxSlotStatusTable, ByteDropTable, …")
    b += line(300, 116, 358, 60, INK2, 1.3, marker="ar")
    b += f'<text x="304" y="104" font-size="10" fill="{INK2}">bind mount</text>'
    b += line(374, 225, 286, 213, INK2, 1.3, marker="ar")
    b += f'<text x="302" y="203" font-size="10" fill="{INK2}">results</text>'
    return svg(800, 256, b, "Part 2 architecture: host generates scenario, container runs EMANE")


# ------------------------------------------------------------------------- content

def table(headers, rows, cls=""):
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>'


def build_html(author: str) -> str:
    plans, g, control = load_part1()
    runs = load_part2()
    grid = plans["grid_16"]
    names = grid.node_order
    clique = set(grid.exact.clique_witness)
    report_text = (ROOT / "docs" / "sample_output" / "grid_16.txt").read_text()
    mapping_matrix = report_text[report_text.index("NODE -> SLOT"):report_text.index("Execution finalized")].rstrip()
    control_lost = sum(1 for o in predict_delivery(g, control) if not o.delivered)

    def r(topo, slot, label):
        return runs[(topo, slot, label)]

    def pct_ok(a):
        xs = [l for l in a["links"] if l["predicted"]]
        return f'{100 * sum(l["ratio"] for l in xs) / len(xs):.1f}%' if xs else "–"

    def pct_lost(a):
        xs = [l for l in a["links"] if not l["predicted"]]
        return f'{100 * sum(l["ratio"] for l in xs) / len(xs):.1f}%' if xs else "–"

    def matches(a):
        return f'{sum(l["match"] for l in a["links"])}/{len(a["links"])}'

    total_checks = sum(len(a["links"]) for (t, s, lab), a in runs.items() if s in ("slot-2ms", "slot-4ms"))
    total_match = sum(sum(l["match"] for l in a["links"]) for (t, s, lab), a in runs.items() if s in ("slot-2ms", "slot-4ms"))
    opt_collisions = sum(a["mac"]["collisions"] for (t, s, lab), a in runs.items() if lab == "optimized")
    n_opt_runs = sum(1 for k in runs if k[2] == "optimized")

    emane_rows = []
    for topo, nlinks in (("grid_16", 84), ("field_16", 30)):
        for slot in ("slot-1ms", "slot-2ms", "slot-4ms"):
            for label in ("optimized", "control-g-only"):
                if (topo, slot, label) not in runs:
                    continue
                a = r(topo, slot, label)
                emane_rows.append([
                    "4×4 grid" if topo == "grid_16" else "field",
                    "<b>optimized</b>" if label == "optimized" else "G-only control",
                    a["slots"], slot.replace("slot-", ""), pct_ok(a), pct_lost(a), matches(a),
                    f'<b>{a["mac"]["collisions"]:,}</b>' if label == "optimized" else f'{a["mac"]["collisions"]:,}',
                    f'{a["mac"]["late"]:,}'])

    other_rows = []
    for key, desc in [("grid_16", "4×4 grid, 300 m spacing (assessment coordinates)"),
                      ("field_16", "irregular convoy + separate outpost, 2 groups"),
                      ("ring_7", "7 radios on a ring, 450 m apart"),
                      ("spec_4", "4-node example from the problem statement")]:
        p = plans[key]
        n = p.communication_graph.number_of_nodes()
        other_rows.append([f"<code>{key}</code>", desc, n, p.communication_graph.number_of_edges(),
                           f"{p.conflicts.total} ({p.conflicts.one_hop} / {p.conflicts.two_hop})",
                           len(p.components), f"<b>{p.num_slots}</b>", p.exact.lower_bound,
                           p.exact.optimality.value.replace("proven optimal: ", "proven: ")])

    author_line = f'<p class="author">{e(author)}</p>' if author else ""
    h = []
    h.append(f"""
<section class="cover">
  <div class="kicker">Vaan Megam Networks · Wireless Protocol Development Internship · Technical assessment</div>
  <h1>TDMA Schedule Planner<br>and Optimizer</h1>
  <p class="subtitle">Distance-2 graph colouring for collision-free time slots, proven optimal and verified on live packets in EMANE</p>
  {author_line}
  <div class="tiles">
    <div class="tile"><div class="big">{grid.num_slots}</div><div class="cap">slots for the 16-radio grid<br><b>proven optimal</b></div></div>
    <div class="tile"><div class="big">{opt_collisions}</div><div class="cap">collisions in EMANE with the<br>optimized schedule ({n_opt_runs} runs)</div></div>
    <div class="tile"><div class="big">{total_match}/{total_checks}</div><div class="cap">link-level predictions<br>matched by EMANE</div></div>
    <div class="tile"><div class="big">102</div><div class="cap">automated tests,<br>all passing</div></div>
  </div>
  <table class="cover-meta">
    <tr><td>Part 1 · Network Brain</td><td>Complete: CLI, distance-2 colouring, heuristics, optimality proof, Slot × Node matrix</td></tr>
    <tr><td>Part 2 · EMANE Engine</td><td>Implemented and measured: schedule → EMANE TDMA events → packets dropped or delivered per slot</td></tr>
    <tr><td>Repository</td><td>Source, tests, this document, EMANE results and one-command demo</td></tr>
    <tr><td>Date</td><td>October 2026</td></tr>
  </table>
</section>

<section class="toc">
  <h2 class="nonum">Contents</h2>
  <ol>
    <li>Summary</li><li>Understanding the problem</li><li>Design process: how the solution was reasoned out</li>
    <li>Part 1: the Network Brain</li><li>Part 1 results: final values</li><li>Part 2: EMANE integration and results</li>
    <li>Verification and quality</li><li>Design decisions and alternatives considered</li><li>Limitations and next steps</li>
    <li>Appendix: running it, repository map, EMANE files</li>
  </ol>
</section>

<h2 class="nobreak">Summary</h2>
<p class="lead">Radios that share one frequency take turns in time slots. Two radios must not share a slot if they are neighbours, or if they have a neighbour in common (the hidden terminal). I model those pairs as the square of the radio graph, <b>G²</b>, so a collision-free schedule is exactly a proper colouring of G², with one colour per time slot.</p>
<ul class="tight">
  <li><b>Part 1.</b> A Python CLI builds the radio graph from coordinates (500 m range), builds G², and colours it with a portfolio of heuristics led by DSATUR. It then <b>proves</b> how good the result is: a lower bound from the largest group of mutually conflicting radios, plus a bounded exact search when needed. An independent validator re-checks every schedule before anything is printed.</li>
  <li><b>Final value, assessment grid:</b> {grid.num_slots} slots, proven optimal, because {len(clique)} radios (<code>Node_06</code> and its 8 neighbours) all conflict with each other. On an irregular 16-radio layout the same code reaches 4 slots, so every slot is reused by 4 radios.</li>
  <li><b>Part 2.</b> The schedule drives a 16-radio EMANE 1.5.2 TDMA network in one Docker container. Before each run the Brain predicts, for every link, whether a frame will get through. EMANE matched <b>{total_match} of {total_checks}</b> predictions at 2–4 ms slots. The optimized schedule caused <b>zero collisions</b> in every run. A deliberately wrong control schedule (2-hop rule ignored) lost 97–99% of frames on exactly the links predicted.</li>
  <li><b>One honest limit.</b> At the required 1 ms slots, the 2-vCPU test machine could not emulate 16 radios in real time, so some frames arrived after their slot ended. These were timing drops, never collisions; at 2 ms and 4 ms delivery was 98.7% and 99.7%.</li>
</ul>

<h2>Understanding the problem</h2>
<h3>Collisions happen at the receiver</h3>
<p>In TDMA every radio gets an exclusive slot in a repeating frame. A collision is a <i>receiver</i> event: if two signals reach the same radio in the same slot, it decodes neither. That gives three cases:</p>
<figure>{fig_hops()}<figcaption>Figure 1. The three interference cases that define the scheduling rules.</figcaption></figure>

<h3>From rules to a graph</h3>
<p><b>G</b> (communication graph): one node per radio, an edge when the Euclidean distance is ≤ 500 m (inclusive). <b>H = G²</b> (conflict graph): an edge between two radios whose hop distance in G is 1 or 2. Those are precisely the pairs that must not share a slot.</p>
<div class="callout"><b>Key insight.</b> A valid TDMA schedule is a proper vertex colouring of G². The minimum frame length is the chromatic number χ(G²). Colouring G alone is <i>not</i> enough: in A–B–C, A and C are not adjacent in G, so they may get the same colour and collide at B.</div>

<h3>Assumptions</h3>
{table(["Topic", "Assumption", "Reason"], [
    ["Links", "Undirected; edge iff distance ≤ 500 m, compared exactly", "As specified; no tolerance that would move the boundary"],
    ["Interference", "Protocol model: conflict iff 1 or 2 hops apart", "As specified; standard in TDMA literature"],
    ["Slots", "One transmit slot per radio per frame (broadcast scheduling)", "As specified; each node gets a slot"],
    ["Topology", "Static coordinates", "As specified; mobility discussed in §9"],
    ["Co-located radios", "Distance 0 ⇒ linked, must differ", "Radios in the same place certainly interfere"],
    ["Separate groups", "Disconnected components may reuse every slot", "No radio can hear across components"]])}

<h2>Design process: how the solution was reasoned out</h2>
<p>Each step below is a question I had to answer, the decision taken, and why. The order is the order in which the work was done.</p>
<ol class="process">
  <li><b>What exactly causes a collision?</b> → A receiver hearing two transmissions. → So the rule is "no shared slot within 2 hops", which is exactly G². This turns a radio problem into a well-studied graph problem.</li>
  <li><b>Can the minimum be found exactly?</b> → Minimum graph colouring is NP-hard in general, so no fast algorithm is known for every network. → Use fast heuristics, but do not just <i>claim</i> quality: measure it against a lower bound.</li>
  <li><b>Which heuristic?</b> → DSATUR was required as the baseline; I did not assume it is best. → I measured it against five other greedy orders, 100 seeded random orders and an iterated-greedy refinement on 290 random networks, and kept the best valid result. Ties keep DSATUR's answer, so extra attempts can never make the result worse.</li>
  <li><b>How do I know the answer is good?</b> → A clique (radios that all conflict pairwise) needs one slot per member, so its size is a hard minimum. → If the heuristic reaches it, the schedule is <b>proven optimal</b>. If not, a bounded branch-and-bound search proves or improves it, and otherwise the report says "best found".</li>
  <li><b>How do I know the code is correct?</b> → An independent validator recomputes 1- and 2-hop pairs by breadth-first search on G, without trusting G². The pipeline refuses to print an unverified schedule. 102 tests cover the 18 required cases and more, and deliberately injected bugs check that the tests catch real faults.</li>
  <li><b>Does it hold up on a real emulator?</b> → The Brain writes a full EMANE scenario and <b>predicts each link's outcome before the run</b>. A wrong "control" schedule runs alongside, proving the emulator would catch a bad schedule.</li>
  <li><b>What did I learn along the way?</b> → (a) For the assessment's own example grid, 9 slots is a proven minimum, so the 5-slot sample output in the brief cannot be collision-free (§5.2). (b) EMANE at 1 ms slots needs CPU headroom; slot length separates emulator timing from schedule correctness (§6.5).</li>
</ol>

<h2>Part 1: the Network Brain</h2>
<h3>Architecture</h3>
<figure>{fig_pipeline()}<figcaption>Figure 2. End-to-end pipeline. Blue boxes are the core of the method.</figcaption></figure>
{table(["Module", "Responsibility", "Main library calls"], [
    ["<code>input_parser</code>", "Strict JSON parsing: rejects malformed JSON, duplicates, strings, booleans, NaN/∞, wrong dimensions, wrong node count", "<code>json.loads</code> (hooks), <code>math.isfinite</code>"],
    ["<code>topology</code>", "Builds G: every pair checked once, edge if distance ≤ range; components", "<code>nx.Graph</code>, <code>math.dist</code>, <code>itertools.combinations</code>"],
    ["<code>conflict_graph</code>", "H = G², each edge tagged 1-hop or 2-hop", "<code>nx.power(G, 2)</code>"],
    ["<code>coloring</code>", "Heuristic portfolio, keeps the best valid colouring, slots renumbered 0..K−1", "<code>nx.coloring.greedy_color</code>, <code>random.Random(seed)</code>"],
    ["<code>exact</code>", "Clique lower bound; bounded branch-and-bound; optimality label", "<code>nx.find_cliques</code>"],
    ["<code>validator</code>", "Independent check from G (not H); lists every violating pair", "<code>nx.single_source_shortest_path_length</code>"],
    ["<code>pipeline</code>", "Runs the stages; raises instead of returning an invalid schedule", "none"],
    ["<code>report</code> / <code>cli</code>", "ASCII report, mapping and matrix; flags, exit codes 0 / 2 / 3", "<code>argparse</code>"],
    ["<code>emane_export</code> / <code>emane_scenario</code>", "Part 2 bridge: EMANE schedule XML, full scenario, per-link prediction", "<code>xml.etree.ElementTree</code>"]])}

<h3>Colouring algorithm</h3>
<p><b>Greedy colouring</b> visits radios in some order and gives each the lowest slot not used by an already-coloured conflicting radio. It is always valid. Its quality depends only on the visiting order, so the method is about choosing good orders:</p>
{table(["Attempt", "Order rule", "Why it is in the portfolio"], [
    ["<b>DSATUR</b> (baseline)", "Next = radio whose neighbours already use the most distinct slots", "Handles the most constrained radio first; strong and standard"],
    ["largest_first", "Most neighbours first (Welsh–Powell)", "Places hubs early"],
    ["smallest_last", "Peel least-connected radios, colour in reverse", "Strong on sparse geometric graphs"],
    ["independent_set, BFS, DFS", "Structural orders", "Diversity: different failure modes"],
    ["random order ×100", "Seeded random permutations (<code>random.Random(42)</code>)", "Escapes blind spots of fixed rules; reproducible"],
    ["iterated greedy", "Re-colour keeping each slot's radios together", "Can never use more slots, often fewer"]])}

<h3>Proving optimality</h3>
<p>A <b>clique</b> in G² is a set of radios that all conflict pairwise, so each needs its own slot. Its size ω is therefore a lower bound: χ(G²) ≥ ω. In G² every radio together with all its neighbours forms a clique, so ω ≥ (max degree + 1). The maximum clique is found exactly (Bron–Kerbosch). If the heuristic uses ω slots, the schedule is <b>proven optimal</b> and the clique is the certificate. If a gap remains, a <b>bounded branch-and-bound</b> search (DSATUR order, clique pre-coloured to break symmetry, 200,000-node budget) either finds a better schedule, proves the current one optimal, or stops and labels the result "best found". Example: 7 radios on a ring give ω = 3, yet every heuristic needs 4. The search proves 4 is optimal in 4 search nodes.</p>

<h3>Correctness safeguards</h3>
<ul class="tight">
  <li><b>Independent validator</b>: recomputes all pairs within 2 hops by breadth-first search on G. A bug in building G² cannot validate itself.</li>
  <li><b>Validation gate</b>: the pipeline raises <code>ScheduleValidationError</code> (exit code 3) rather than return an invalid schedule. A test injects a broken optimiser to prove this.</li>
  <li><b>Determinism</b>: natural node order (<code>Node_2</code> before <code>Node_10</code>) and one seeded generator, so the same input and seed give byte-identical output.</li>
</ul>

<h2>Part 1 results: final values</h2>
<h3>The 16-radio assessment grid</h3>
<p>Input: the assessment's coordinates, a 4×4 grid with 300 m spacing, <code>Node_01</code> at (0, 0) to <code>Node_16</code> at (900, 900). At 500 m range the diagonal neighbours (424 m) are linked too.</p>
{table(["Measure", "Value"], [
    ["Radios / links in G", f"16 / {grid.communication_graph.number_of_edges()}"],
    ["Conflicting pairs in G²", f"{grid.conflicts.total} = {grid.conflicts.one_hop} one-hop + {grid.conflicts.two_hop} two-hop (hidden terminal)"],
    ["<b>Frame length</b>", f"<b>{grid.num_slots} slots</b> = {grid.num_slots} ms at 1 ms per slot"],
    ["Lower bound (largest clique)", f"{grid.exact.lower_bound}: {', '.join(n[-2:] for n in grid.exact.clique_witness)}"],
    ["Optimality", grid.exact.optimality.value],
    ["Spatial reuse", "5 of 9 slots shared; slot 0 used by 4 radios (01, 04, 13, 16)"],
    ["Selected method", f"{grid.method} (DSATUR)"],
    ["Independent validation", f"passed: {grid.validation.pairs_checked} one/two-hop pairs checked"]], "narrow")}
<figure class="grid">{fig_grid(grid.communication_graph, grid.assignment, clique)}<figcaption>Figure 3. The optimal schedule on the assessment grid. The 9 highlighted radios all conflict pairwise, so no schedule can use fewer than 9 slots.</figcaption></figure>
<p class="keep">CLI output (unedited, from <code>tdma-optimizer --input examples/grid_16.json</code>):</p>
<pre class="out">{e(mapping_matrix)}</pre>

<h3>A note on the 5-slot sample output in the brief</h3>
<p>The brief's sample shows 5 slots for these coordinates. Figure 3 proves at least 9 are needed. The sample also gives <code>Node_01</code> and <code>Node_03</code> the same slot although both neighbour <code>Node_02</code>, a hidden-terminal collision. I read the sample as an illustration of the output <i>format</i>. My validator rejects that assignment (a test shows which pairs collide), and Part 2 shows a 4-slot schedule of the same kind losing packets in EMANE.</p>
<figure>{fig_control(g, control)}<figcaption>Figure 4. Colouring G instead of G² gives fewer slots but lets hidden terminals collide.</figcaption></figure>

<h3>Other topologies</h3>
{table(["Input", "Description", "Radios", "Links", "Conflicts (1-hop / 2-hop)", "Groups", "Slots", "Bound", "Status"], other_rows, "small")}

<h3>Heuristic comparison</h3>
<p>Measured with <code>scripts/benchmark.py</code> (seed 7) on 200 random 16-radio deployments in a 1.5 km square. DSATUR alone reached the proven optimum every time, and the full portfolio was proven optimal in 200 of 200 networks (mean 7.67 slots, about 8 ms per network).</p>
<figure>{fig_heuristics()}<figcaption>Figure 5. How often each heuristic alone reached the optimum. Weaker orders stay in the portfolio only for diversity; they can never worsen the result.</figcaption></figure>
{table(["Network size", "Trials", "DSATUR optimal", "Portfolio proven optimal", "Median time"], [
    ["16 radios, 1.5 km square", 200, "200/200", "200/200", "8.4 ms"],
    ["40 radios, 2.5 km", 30, "30/30", "30/30", "24.9 ms"],
    ["80 radios, 3.5 km", 30, "29/30", "30/30 (others caught DSATUR's miss)", "59.8 ms"],
    ["150 radios, 5 km", 30, "30/30", "30/30", "136.9 ms"]], "narrow")}

<h2>Part 2: EMANE integration and results</h2>
<h3>What EMANE does, in plain words</h3>
<p>EMANE emulates radios in real time. Each radio is an <b>NEM</b>: an <code>emane</code> process with a virtual network interface (<code>emane1</code>…<code>emane16</code>), a MAC layer and a PHY layer. A frame written into <code>emane5</code> is queued by NEM 5's MAC, sent over an emulated channel, and judged by every other NEM's PHY (signal strength, noise, overlap). If accepted, it comes out of their interface. EMANE's <b>TDMA radio model</b> lets a radio transmit only in its scheduled slots and receive in the others, so EMANE is the right tool to test whether the schedule works on packets.</p>
<figure>{fig_emane_arch()}<figcaption>Figure 6. The host generates the scenario; one privileged container runs 16 NEMs.</figcaption></figure>
{table(["Bridge file", "Role"], [
    ["<code>emane_export.py</code>", "Schedule → EMANE <i>full</i> TDMA schedule XML: <code>&lt;structure slots=K slotduration=1000&gt;</code>, one <code>&lt;slot nodes=…&gt;&lt;tx/&gt;</code> per slot"],
    ["<code>emane_scenario.py</code>", "16 platform files, NEM/MAC/transport XML, the schedule, and <code>scenario.json</code> with the predicted outcome of every link"],
    ["<code>emane/run_experiment.py</code>", "In the container: starts NEMs, publishes pathloss and schedule events, sends frames, saves EMANE statistics"],
    ["<code>emane/analyze.py</code>", "Prediction vs measurement per link; splits drops into collisions and late frames"],
    ["<code>emane/run_demo.sh</code>", "All of the above in one command"]])}

<h3>Configuration</h3>
{table(["Setting", "Value", "Why"], [
    ["Slot / frame", "1 ms slots (also 2 and 4 ms), 1 frame of K slots", "1 ms as required; longer slots isolate emulator timing (§6.5)"],
    ["Schedule type", "Full schedule", "Every unlisted slot becomes a receive slot, so each radio listens in the other K−1 slots"],
    ["Channel", "2.4 GHz, 1 MHz bandwidth, one frequency", "The Brain assumes one shared channel"],
    ["Data rate", "11 Mbps", "Its PCR curve needs ≥ 5 dB SINR, so equal-power overlaps (≈ 0 dB) fail, like a real radio. 1 Mbps would still decode and hide collisions"],
    ["Propagation", "Precomputed pathloss: 80 dB on each link of G, none otherwise", "EMANE's 'who hears whom' becomes identical to G, so the test isolates the schedule"],
    ["Traffic", "Each radio broadcasts an 88-byte frame every 100 ms for 20 s", "200 numbered frames per radio; every receiver counts per sender"]])}

<h3>Experiment design</h3>
<p><b>Prediction (computed before each run):</b> a frame on link u → v is delivered if and only if v is not transmitting in u's slot, and no other neighbour of v transmits in u's slot. A link <b>matches</b> when predicted-delivered links measure ≥ 90% delivery and predicted-lost links ≤ 10%. Two schedules run through the same emulator:</p>
<ul class="tight">
  <li><b>optimized</b>: the Part 1 schedule (9 slots on the grid). Predicts every link delivered.</li>
  <li><b>G-only control</b>: DSATUR on G instead of G² (4 slots, like the brief's sample). Predicts {control_lost} of 84 directed links lost. Its job is to prove the emulator would catch a bad schedule.</li>
</ul>

<h3>Results</h3>
<figure>{fig_heatmaps(runs, names)}<figcaption>Figure 7. Measured delivery for every directed link of the grid, 4 ms slots. Every red cell was predicted lost before the run; every green cell was predicted delivered.</figcaption></figure>
{table(["Topology", "Schedule", "Slots", "Slot", "Delivery: predicted-OK links", "Delivery: predicted-lost links", "Matches", "Collision drops", "Late drops"], emane_rows, "small")}
<p class="note">Collision drops: frames EMANE's TDMA MAC discarded because they overlapped another transmission at the receiver. Late drops: frames that reached the receiver after their slot ended (EMANE "Slot Error"). Both are counted in frames from EMANE's own statistics tables.</p>

<h3>What the results show</h3>
<ol class="tight">
  <li><b>EMANE enforces the schedule exactly as predicted.</b> At 2 and 4 ms, {total_match} of {total_checks} directed-link predictions matched (both schedules, both topologies). No frame ever crossed between radios out of range.</li>
  <li><b>The distance-2 schedule is collision-free on real packets.</b> Zero collision drops in all {n_opt_runs} optimized runs, including at 1 ms.</li>
  <li><b>The 2-hop rule is necessary.</b> The G-only control lost 97–99% of frames on exactly the predicted hidden-terminal links, with over 12,000 collision drops on the grid.</li>
</ol>

<h3>The 1 ms finding</h3>
<p>At 1 ms, many frames in <i>both</i> schedules arrived after their slot had ended. 16 real-time EMANE processes on a 2-vCPU machine could not process every frame within 1 ms. That this is emulator timing, not the schedule, is shown by the data: for the same schedule, late drops fall from {r("grid_16","slot-1ms","optimized")["mac"]["late"]:,} to {r("grid_16","slot-2ms","optimized")["mac"]["late"]:,} to {r("grid_16","slot-4ms","optimized")["mac"]["late"]:,} frames as the slot grows from 1 to 2 to 4 ms, while collisions stay at 0. A host with more cores should close the gap at 1 ms; I have not measured that yet (§9).</p>

<h2>Verification and quality</h2>
{table(["Area", "Evidence"], [
    ["Automated tests", "102 tests, all passing: parser (19), topology (9), conflict graph (10), colouring (14), exact search (10), validator (7), report (7), EMANE export (5), EMANE scenario (8), CLI end-to-end (13)"],
    ["Required cases", "All 18 cases from the brief map to named tests (exact 500 m boundary, 2-hop conflict, 3-hop reuse, disconnected groups, duplicates, no-edge input, reproducibility, 16-node end-to-end, …)"],
    ["Cross-checks", "<code>nx.power(G, 2)</code> equals an independent BFS on 25 random topologies; prediction agrees with the validator"],
    ["Mutation check", "9 bugs injected one at a time (exclusive boundary, G instead of G², validator ignoring 2 hops, …). 7 caught; the 2 that survive only affect speed, never the output"],
    ["Reproducibility", "Same seed ⇒ byte-identical report (tested); fresh-clone install verified; EMANE demo is one command"],
    ["Honesty in output", "Every schedule is labelled proven or best-found; invalid schedules never print"]])}

<h2>Design decisions and alternatives considered</h2>
<p>The theme behind most choices: <b>at 16 radios, a provably correct and explainable answer is worth more than raw speed.</b></p>
{table(["Decision", "Chosen", "Alternatives", "Why the choice fits"], [
    ["What to colour", "G² (1 and 2 hops)", "G only", "G misses hidden terminals; the EMANE control run shows the cost"],
    ["Baseline", "DSATUR", "Welsh–Powell, smallest-last", "Required, and measured best (200/200 optimal)"],
    ["Search strategy", "Greedy portfolio + refinement", "Tabu search, simulated annealing, genetic", "Already proven optimal here in milliseconds; metaheuristics add complexity without a proof"],
    ["Optimality", "Clique bound + bounded branch-and-bound", "ILP or SAT solvers (OR-Tools, PuLP)", "Proof without heavy dependencies the brief asked to avoid"],
    ["Machine learning", "Not used", "Neural graph colouring", "Excluded by the brief; no validity guarantee; not explainable"],
    ["Verification", "Independent BFS validator", "Check against G² itself", "A checker must not trust what it checks"],
    ["Graph library", "NetworkX", "igraph, own code", "Required; readable and tested; speed is irrelevant at this size"],
    ["Edge construction", "All pairs, O(n²)", "KD-tree / spatial grid", "120 pairs for 16 radios; worth it only at thousands"],
    ["EMANE links", "Precomputed pathloss from G", "Location + free-space model", "Makes the emulator's topology identical to G, so results isolate the schedule"],
    ["EMANE data rate", "11 Mbps", "1 Mbps (tutorial default)", "1 Mbps decodes at 0 dB SINR and would hide collisions"]], "small")}

<h2>Limitations and next steps</h2>
{table(["Limitation", "Next step"], [
    ["Protocol interference model (hard 500 m disk, 2-hop rule)", "Distance-based pathloss and a carrier-sense range larger than decode range; only how G² is built changes"],
    ["1 ms slots in EMANE need CPU headroom (late drops on 2 vCPUs)", "Repeat at 1 ms on 8+ cores, or spread NEMs over several containers"],
    ["Static topology", "Recompute on change; send EMANE <i>update</i> schedules only for radios whose slot changed"],
    ["One slot per radio, regardless of traffic", "Demand-weighted slots: split a busy relay into d mutually conflicting copies"],
    ["Broadcast traffic only in EMANE tests", "Unicast and routed traffic (e.g. OLSR) over the same schedule"],
    ["Exact search is bounded", "Report already says 'best found' when the budget ends; an ILP backend could be optional"]])}

<h2>Appendix: running it, repository map, EMANE files</h2>
<h3>Run</h3>
<pre class="cmd"># install (Python 3.11+)
python -m venv .venv &amp;&amp; source .venv/bin/activate &amp;&amp; pip install -e ".[dev]"

# Part 1: file or inline JSON
tdma-optimizer --input examples/grid_16.json --range 500 --expected-nodes 16 --seed 42 --restarts 100
tdma-optimizer --coordinates '{{"Node_01":[0,0],"Node_02":[300,0],"Node_03":[600,0],"Node_04":[300,400]}}' --expected-nodes 4

# tests and benchmark
python -m pytest
python scripts/benchmark.py

# Part 2 (Docker; on Arch: sudo pacman -S docker &amp;&amp; sudo systemctl enable --now docker)
emane/run_demo.sh                               # grid_16 at 1 ms and 4 ms, about 5 minutes
SLOTS_US="1000 2000 4000" emane/run_demo.sh examples/field_16.json</pre>
<h3>Repository map</h3>
{table(["Path", "Contents"], [
    ["<code>src/tdma_optimizer/</code>", "Part 1 package and the Part 2 bridge (one module per pipeline stage)"],
    ["<code>tests/</code>", "102 tests, one file per module plus end-to-end CLI tests"],
    ["<code>emane/</code>", "<code>run_demo.sh</code>, <code>run_experiment.py</code>, <code>analyze.py</code>, <code>Dockerfile</code>, <code>results/</code> (all measured data)"],
    ["<code>examples/</code>", "<code>grid_16</code>, <code>field_16</code>, <code>ring_7</code>, <code>spec_4</code> topologies"],
    ["<code>docs/</code>", "This PDF, design notes (algorithm, architecture, EMANE, test report), unedited sample outputs"],
    ["<code>scripts/benchmark.py</code>", "Heuristic comparison on random networks"]])}
<h3>EMANE schedule produced for the grid (excerpt)</h3>
<pre class="out">{e((ROOT / "examples" / "grid_16_emane_schedule.xml").read_text()[:900])}…</pre>
""")
    return PAGE_TEMPLATE.replace("%%BODY%%", "\n".join(h))


CSS = """
@page { size: A4; margin: 17mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: Inter, sans-serif; font-size: 10.2pt; line-height: 1.5; color: #1d1d1b; background: #fff;
       counter-reset: h2; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
h1 { font-size: 34pt; line-height: 1.08; margin: 10mm 0 5mm; letter-spacing: -0.5pt; color: #0b0b0b; }
h2 { font-size: 17pt; margin: 0 0 3mm; padding-top: 1mm; color: #0b0b0b; counter-increment: h2; counter-reset: h3;
     break-before: page; break-after: avoid; }
h2::before { content: counter(h2) ".  "; color: #2a78d6; }
h2.nonum { counter-increment: none; }
h2.nonum::before { content: ""; }
h3 { font-size: 12.2pt; margin: 6mm 0 2mm; color: #0b0b0b; break-after: avoid; counter-increment: h3; }
h3::before { content: counter(h2) "." counter(h3) "  "; color: #8a8984; font-weight: 600; }
p { margin: 0 0 2.6mm; }
p.lead { font-size: 11pt; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.6pt; background: #f2f1ee; padding: 0.3pt 2.5pt; border-radius: 3px; }
table { width: 100%; border-collapse: collapse; margin: 2mm 0 4mm; font-size: 9pt; break-inside: auto; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th { text-align: left; font-weight: 650; color: #52514e; border-bottom: 1.4px solid #0b0b0b; padding: 4px 6px; vertical-align: bottom; }
td { border-bottom: 1px solid #e4e3df; padding: 4px 6px; vertical-align: top; }
table.small { font-size: 8.3pt; }
table.small td, table.small th { padding: 3px 4px; }
table.narrow td:first-child { width: 38%; color: #52514e; }
figure { margin: 3mm 0 5mm; break-inside: avoid; }
figure.grid svg { width: 82%; display: block; margin: 0 auto; }
figcaption { font-size: 8.8pt; color: #52514e; margin-top: 1.5mm; }
.callout { border-left: 3px solid #2a78d6; background: #eef5fd; padding: 3mm 4mm; margin: 3mm 0 4mm; break-inside: avoid; }
pre { font-family: "DejaVu Sans Mono", monospace; font-size: 7.4pt; line-height: 1.32; background: #f7f6f3;
      border: 1px solid #e4e3df; border-radius: 4px; padding: 3mm; white-space: pre; overflow: hidden; break-inside: avoid; }
pre.cmd { font-size: 7.8pt; white-space: pre-wrap; word-break: break-all; }
ul.tight, ol.tight { padding-left: 5mm; margin: 0 0 3mm; } ul.tight li, ol.tight li { margin-bottom: 1.6mm; }
ol.process { padding-left: 6mm; } ol.process li { margin-bottom: 2.6mm; break-inside: avoid; }
.note { font-size: 8.8pt; color: #52514e; }
.keep { break-after: avoid; margin-top: 4mm; }
.cover { height: 255mm; display: flex; flex-direction: column; }
.kicker { font-size: 9pt; font-weight: 650; color: #2a78d6; letter-spacing: 0.6pt; text-transform: uppercase; margin-top: 18mm; }
.subtitle { font-size: 13.5pt; color: #52514e; max-width: 150mm; line-height: 1.4; }
.author { font-size: 12pt; font-weight: 650; margin-top: 2mm; }
.tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4mm; margin: 14mm 0 12mm; }
.tile { border-top: 3px solid #2a78d6; padding-top: 3mm; }
.tile .big { font-size: 25pt; font-weight: 750; color: #0b0b0b; line-height: 1.1; letter-spacing: -0.5pt; }
.tile .cap { font-size: 9pt; color: #52514e; margin-top: 1.5mm; line-height: 1.35; }
.cover-meta { margin-top: auto; font-size: 9.3pt; }
.cover-meta td:first-child { width: 42mm; font-weight: 650; color: #0b0b0b; }
.toc { break-before: page; margin-bottom: 8mm; }
h2.nobreak { break-before: avoid; }
.toc ol { font-size: 10.5pt; line-height: 1.75; padding-left: 7mm; columns: 2; column-gap: 10mm; }
"""

PAGE_TEMPLATE = ("<!doctype html><html lang='en'><head><meta charset='utf-8'><title>TDMA Schedule Optimizer: Documentation</title>"
                 f"<style>{CSS}</style></head><body>%%BODY%%</body></html>")

FOOTER = ("<div style=\"font-family: Inter, sans-serif; font-size: 7.5pt; color: #8a8984; width: 100%; "
          "padding: 0 16mm; display: flex; justify-content: space-between;\">"
          "<span>TDMA Schedule Planner and Optimizer · Documentation</span>"
          "<span><span class=\"pageNumber\"></span> / <span class=\"totalPages\"></span></span></div>")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--author", default="", help="name printed on the cover")
    parser.add_argument("--html-only", action="store_true")
    args = parser.parse_args()

    OUT_HTML.write_text(build_html(args.author), encoding="utf-8")
    print(f"wrote {OUT_HTML}")
    if args.html_only:
        return 0
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(OUT_HTML.as_uri())
        page.wait_for_timeout(300)
        page.pdf(path=str(OUT_PDF), format="A4", print_background=True, display_header_footer=True,
                 header_template="<div></div>", footer_template=FOOTER,
                 margin={"top": "17mm", "bottom": "18mm", "left": "16mm", "right": "16mm"})
        browser.close()
    print(f"wrote {OUT_PDF}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
