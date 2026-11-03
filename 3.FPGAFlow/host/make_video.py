"""Animated results video (1920x1080 MP4): my neuron-expansion design vs the standard multi-bit
approach, ending on a hand-off to the live FPGA test. Every number is read from the result files.

  python host/make_video.py                  -> portfolio/results_video.mp4
  python host/make_video.py --preview 5      -> only render scene 5 (fast check)
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import imageio_ffmpeg
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

from make_figures import (AQUA, BLUE, GRID, INK, INK2, MUTED, ORANGE, SURFACE, gather, load_jsonl, ms,
                          xnor_bits)

FPS = 30
W, H, DPI = 16, 9, 120
MINE, STD, PLAIN = ORANGE, BLUE, MUTED   # my design / standard multi-bit / plain-binary controls
OUT = Path("portfolio/results_video.mp4")

plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": INK2, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "font.size": 18})


# ----------------------------------------------------------------------------- data

def data():
    D = gather()
    study = load_jsonl(Path("results/study.jsonl"))
    kterm = defaultdict(list)
    kbits = {}
    for r in study:
        sl = r.get("salient_layers") or []
        if (r["model"] == "expanded" and r["hidden"] == [128, 128] and r.get("k") == 3 and sl and sl[1] == 0
                and sl[2] == 0 and r["saliency"] in ("awq",)):
            n = len(r["salient_channels"][0])
            kterm[n].append(r["test_ler"])
            kbits[n] = xnor_bits(r)
    nexp = defaultdict(list)
    nbits = {}
    for r in D["nexp"]:
        key = ("plain" if r.get("plain") else r["saliency"], r["schedule"], r["n_sal"])
        nexp[key].append(r["test_ler"])
        nbits[key] = r["xnor_bits"]

    md = Path("results/analysis_nexp.md").read_text(encoding="utf-8")
    knock = {}
    for m in re.finditer(r"\| uniform \| (\w+) \| 12 \| ([\d.]+) \| ([\d.]+) \|", md):
        knock[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    learned = {}
    for m in re.finditer(r"\| (±[\d±]+) \| ±(\d) \| (.+?) \|", md):
        cnt = {int(v): int(c) for v, c in re.findall(r"([+-]\d+): (\d+)", m.group(3))}
        learned[int(m.group(2))] = cnt
    return dict(D=D, kterm={n: ms(v) for n, v in kterm.items()}, kbits=kbits,
                nexp={k: ms(v) for k, v in nexp.items()}, nbits=nbits, knock=knock, learned=learned)


# ----------------------------------------------------------------------------- helpers

def ease(t, start, dur=0.6):
    """0 -> 1 between start and start+dur (smoothstep)."""
    x = np.clip((t - start) / dur, 0, 1)
    return x * x * (3 - 2 * x)


def header(fig, title, sub=None, a=1.0):
    fig.text(0.05, 0.9, title, fontsize=38, fontweight="bold", color=INK, alpha=a)
    if sub:
        fig.text(0.05, 0.845, sub, fontsize=21, color=INK2, alpha=a)


def caption(fig, text, a, y=0.06, color=INK, size=22, weight="bold"):
    if a > 0:
        fig.text(0.05, y, text, fontsize=size, color=color, alpha=a, fontweight=weight)


def pct(ax):
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=1))


# ----------------------------------------------------------------------------- scenes

def s_title(fig, t, V):
    a = ease(t, 0.2, 0.8)
    fig.text(0.05, 0.62, "Can extra neurons fix a", fontsize=56, fontweight="bold", color=INK, alpha=a)
    fig.text(0.05, 0.52, "binary neural network?", fontsize=56, fontweight="bold", color=MINE, alpha=a)
    b = ease(t, 1.2, 0.8)
    fig.text(0.05, 0.40, "Testing my own design for a quantum error-correction decoder on an FPGA",
             fontsize=24, color=INK2, alpha=b)
    fig.text(0.05, 0.12, "distance-3 surface code  ·  Stim + PyTorch + Verilog  ·  Spartan-7 XC7S25",
             fontsize=18, color=MUTED, alpha=b)


def s_problem(fig, t, V):
    D = V["D"]
    header(fig, "The problem", "A binary network (every weight ±1) is tiny and fast in hardware, but it loses accuracy")
    ax = fig.add_axes([0.30, 0.2, 0.62, 0.55])
    rows = [("Plain binary network", ms(D["bnn"][128])[0], PLAIN, 2.0),
            ("PyMatching (standard)", D["mwpm"], INK2, 1.0),
            ("Full-precision network", D["fp"][128], AQUA, 0.0)]
    for i, (lab, v, c, delay) in enumerate(rows):
        g = ease(t, 0.5 + delay, 1.0)
        ax.barh(i, v * g, color=c, height=0.6)
        if g > 0.95:
            ax.text(v + 0.0004, i, f"{v * 100:.2f}%", va="center", fontsize=24, fontweight="bold", color=INK)
    ax.set_yticks(range(3), [r[0] for r in rows], fontsize=22)
    ax.set_xlim(0, 0.034)
    ax.grid(axis="y", visible=False)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=1))
    ax.set_xlabel("logical error rate (lower is better)")
    caption(fig, "Goal: win back the lost accuracy while keeping the hardware small.", ease(t, 4.5))


def _net(ax, x0, highlight_extra, color, label, a):
    """Tiny network sketch: 5 detectors -> 6 neurons; detector 2 is the salient one."""
    det = [(x0, 0.85 - i * 0.14) for i in range(5)]
    hid = [(x0 + 0.22, 0.88 - i * 0.12) for i in range(6)]
    for (dx, dy) in det:
        for (hx, hy) in hid:
            ax.plot([dx, hx], [dy, hy], color=GRID, lw=1, alpha=a, zorder=1)
    if highlight_extra:
        labs = ["±2", "±2", "±4", "±4", "±7"]
        ext = [(x0 + 0.40, 0.80 - i * 0.14) for i in range(5)]
        for (hx, hy), l in zip(ext, labs):
            ax.plot([det[2][0], hx], [det[2][1], hy], color=color, lw=3.5, alpha=a, zorder=2)
            ax.plot(hx, hy, "o", ms=30, color=color, alpha=a, zorder=3)
            ax.text(hx + 0.04, hy, l, va="center", fontsize=20, color=INK, fontweight="bold", alpha=a)
    else:
        for (hx, hy) in hid:
            ax.plot([det[2][0], hx], [det[2][1], hy], color=color, lw=3.5, alpha=a, zorder=2)
    for i, (dx, dy) in enumerate(det):
        ax.plot(dx, dy, "o", ms=26, color=color if i == 2 else MUTED, alpha=a, zorder=3)
    for (hx, hy) in hid:
        ax.plot(hx, hy, "o", ms=26, color=MUTED, alpha=a, zorder=3)
    ax.text(x0 - 0.02, 1.0, label, fontsize=24, fontweight="bold", color=color, alpha=a)


def s_ideas(fig, t, V):
    header(fig, "Two ways to add precision where it matters",
           "Rank detectors by how active they are (AWQ-style), then give the top ones finer weights")
    ax = fig.add_axes([0.04, 0.05, 0.92, 0.72])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    _net(ax, 0.05, True, MINE, "My design: dedicated neurons", ease(t, 0.5))
    _net(ax, 0.60, False, STD, "Standard: multi-bit weights", ease(t, 3.5))
    a = ease(t, 0.5)
    ax.text(0.03, 0.02, "each salient detector gets 5 extra\nneurons with wider weight ranges", fontsize=17,
            color=INK2, alpha=a)
    b = ease(t, 3.5)
    ax.text(0.58, 0.02, "the salient detector's weight in every existing\nneuron gets 3 bits: ±1, ±3, ±5 or ±7", fontsize=17,
            color=INK2, alpha=b)


def s_fair(fig, t, V):
    header(fig, "A fair test")
    items = [("90", "networks trained for my design (5 random seeds each)"),
             ("3 · 6 · 12", "salient detectors, two different unit mixes"),
             ("Control 1", "pick the detectors at random instead of by AWQ"),
             ("Control 2", "same extra neurons, but only plain ±1 weights"),
             ("1,000,000", "fresh test shots for every network, compared with PyMatching")]
    for i, (big, txt) in enumerate(items):
        a = ease(t, 0.4 + 1.0 * i)
        y = 0.72 - i * 0.13
        fig.text(0.07, y, big, fontsize=34, fontweight="bold", color=MINE if i < 2 else INK, alpha=a)
        fig.text(0.30, y + 0.005, txt, fontsize=26, color=INK2, alpha=a)


def s_result1(fig, t, V):
    D, nx = V["D"], V["nexp"]
    header(fig, "Result 1: my design helps...", "Error rate vs number of salient detectors (uniform unit mix, mean of 5 seeds)")
    ax = fig.add_axes([0.08, 0.2, 0.62, 0.58])
    ns = [3, 6, 12]
    series = [("awq", "my design (AWQ-ranked)", MINE, "o", 0.5), ("random", "control: random detectors", INK2, "s", 3.5),
              ("plain", "control: plain ±1 neurons", PLAIN, "^", 5.0)]
    bnn = ms(D["bnn"][128])[0]
    ax.axhline(bnn, color=PLAIN, ls=(0, (4, 3)), lw=2)
    ax.text(12.3, bnn, "plain binary\nnetwork", va="center", fontsize=16, color=INK2)
    ax.axhline(D["mwpm"], color=INK, ls=(0, (2, 2)), lw=1.5)
    ax.text(12.3, D["mwpm"] + 0.0002, "PyMatching", va="bottom", fontsize=16, color=INK2)
    for key, lab, c, mk, start in series:
        g = ease(t, start, 1.2)
        if g <= 0:
            continue
        m = [nx[(key, "uniform", n)][0] for n in ns]
        s = [nx[(key, "uniform", n)][1] for n in ns]
        k = g * (len(ns) - 1)
        i = int(k)
        xs, ys = ns[:i + 1], m[:i + 1]
        if i < len(ns) - 1:
            f = k - i
            xs = xs + [ns[i] + f * (ns[i + 1] - ns[i])]
            ys = ys + [m[i] + f * (m[i + 1] - m[i])]
        ax.plot(xs, ys, color=c, lw=3.5, label=lab)
        ax.errorbar(ns[:i + 1], m[:i + 1], yerr=s[:i + 1], fmt=mk, color=c, ms=14, capsize=5, mec=SURFACE, mew=2)
    ax.set_xticks(ns)
    ax.set_xlim(2, 13.5)
    ax.set_ylim(0.0160, 0.0300)
    pct(ax)
    ax.set_xlabel("salient detectors")
    ax.set_ylabel("logical error rate")
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 0.2), fontsize=17, frameon=False)
    best = nx[("awq", "uniform", 12)][0]
    a = ease(t, 1.8)
    fig.text(0.74, 0.62, f"{bnn * 100:.2f}% → {best * 100:.2f}%", fontsize=30, fontweight="bold", color=MINE, alpha=a)
    fig.text(0.74, 0.57, "vs the plain binary network", fontsize=18, color=INK2, alpha=a)
    caption(fig, "...but the controls do almost as well: most of the gain is just from adding neurons.",
            ease(t, 7.0), color=INK)


def s_knockout(fig, t, V):
    kn = V["knock"]
    header(fig, "Look inside: switch the extra neurons off",
           "12 salient detectors, error rate with the dedicated neurons working vs disconnected")
    ax = fig.add_axes([0.08, 0.2, 0.84, 0.56])
    groups = [("awq", "my design", MINE), ("random", "random detectors", INK2), ("plain", "plain ±1 neurons", PLAIN)]
    for i, (k, lab, c) in enumerate(groups):
        on, off = kn[k]
        g1, g2 = ease(t, 0.4 + 0.3 * i, 0.8), ease(t, 2.5 + 0.4 * i, 0.8)
        ax.bar(i - 0.18, on * g1, 0.34, color=c)
        ax.bar(i + 0.18, off * g2, 0.34, color=c, alpha=0.35, hatch="//", edgecolor=c)
        if g1 > 0.95:
            ax.text(i - 0.18, on + 0.0006, f"{on * 100:.2f}%", ha="center", fontsize=19, color=INK)
        if g2 > 0.95:
            ax.text(i + 0.18, off + 0.0006, f"{off * 100:.2f}%\n(+{(off / on - 1) * 100:.0f}%)", ha="center",
                    fontsize=19, color=INK, fontweight="bold")
    ax.set_xticks(range(3), [f"{l}\nworking  |  off" for _, l, _ in groups], fontsize=19)
    ax.set_ylim(0, 0.045)
    ax.grid(axis="x", visible=False)
    pct(ax)
    ax.set_ylabel("logical error rate")
    caption(fig, "The network relies on them, but almost as much on the plain ±1 versions.",
            ease(t, 5.5))


def s_learned(fig, t, V):
    L = V["learned"]
    header(fig, "What weights did training actually choose?",
           "Weight each dedicated neuron learned on its own salient detector (all 60 trained models)")
    ax = fig.add_axes([0.16, 0.22, 0.78, 0.52])
    order = [(7, "±7 unit"), (4, "±4 unit"), (2, "±2 unit")]
    cats = [("max negative", lambda v, r: v == -r, STD), ("zero: ignores its detector", lambda v, r: v == 0, ORANGE),
            ("max positive", lambda v, r: v == r, AQUA), ("in between", lambda v, r: 0 < abs(v) < r, MUTED)]
    for i, (r, lab) in enumerate(order):
        cnt = L[r]
        tot = sum(cnt.values())
        g = ease(t, 0.4 + 0.8 * i, 1.0)
        left = 0.0
        for name, f, c in cats:
            share = sum(n for v, n in cnt.items() if f(v, r)) / tot
            w = share * g
            ax.barh(i, w, left=left, color=c, height=0.62, edgecolor=SURFACE, lw=2,
                    label=name if i == 0 else None)
            if g > 0.95 and share > 0.07:
                ax.text(left + w / 2, i, f"{share * 100:.0f}%", ha="center", va="center", fontsize=21,
                        fontweight="bold", color="white")
            left += w
    ax.set_yticks(range(3), [l for _, l in order], fontsize=22)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.grid(visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.1), ncol=4, fontsize=17, frameon=False)
    caption(fig, "±7 units max out as intended. A third of ±2/±4 units learn 0: wasted hardware.",
            ease(t, 4.5))


def s_cost(fig, t, V):
    D = V["D"]
    header(fig, "Head to head: accuracy vs hardware cost",
           "XNOR bits per decode (the hardware cost) vs error rate, 128-wide networks, mean of 5 seeds")
    ax = fig.add_axes([0.09, 0.2, 0.82, 0.56])
    bnn_m = ms(D["bnn"][128])[0]
    ax.axhline(D["mwpm"], color=INK, ls=(0, (2, 2)), lw=1.5)
    ax.text(31.2, D["mwpm"] - 0.0004, "PyMatching", fontsize=16, color=INK2, va="top", ha="right")
    b0 = D["bits"][("bnn", 128)] / 1000
    ax.plot([b0], [bnn_m], "D", color=PLAIN, ms=16, mec=SURFACE, mew=2)
    ax.annotate("plain binary network", (b0, bnn_m), (b0 + 0.3, bnn_m + 0.0007), fontsize=16, color=INK2)
    for key, pts, c, mk, lab, start in (
            ("mine", [(V["nbits"][("awq", "uniform", n)] / 1000, V["nexp"][("awq", "uniform", n)][0], n)
                      for n in (3, 6, 12)], MINE, "o", "my design: dedicated neurons", 1.0),
            ("std", [(V["kbits"][n] / 1000, V["kterm"][n][0], n) for n in sorted(V["kterm"]) if n >= 3],
             STD, "s", "standard: 3-bit weights", 3.5)):
        g = ease(t, start, 1.5)
        if g <= 0:
            continue
        k = max(1, int(np.ceil(g * len(pts))))
        xs, ys, ns = zip(*pts[:k])
        ax.plot(xs, ys, color=c, lw=3.5, marker=mk, ms=15, mec=SURFACE, mew=2, label=lab)
        for x, y, n in pts[:k]:
            ax.annotate(f"{n} det.", (x, y), (14, 0), textcoords="offset points", fontsize=15, color=INK2,
                        va="center")
    ax.set_xlim(19, 31.5)
    ax.set_ylim(0.0155, 0.0300)
    pct(ax)
    ax.set_xlabel("hardware cost: thousands of XNOR bits per decode")
    ax.set_ylabel("logical error rate")
    if ax.get_legend_handles_labels()[0]:
        ax.legend(loc="upper right", fontsize=18, frameon=False)
    caption(fig, "At every cost, standard multi-bit weights reach a lower error rate.", ease(t, 6.5))


def s_verdict(fig, t, V):
    D = V["D"]
    mine = V["nexp"][("awq", "uniform", 12)][0]
    std = V["kterm"][24][0]
    header(fig, "Verdict")
    a, b = ease(t, 0.4), ease(t, 1.6)
    fig.text(0.07, 0.62, f"{mine * 100:.2f}%", fontsize=80, fontweight="bold", color=MINE, alpha=a)
    fig.text(0.07, 0.55, "my design, best setting", fontsize=24, color=INK2, alpha=a)
    fig.text(0.50, 0.62, f"{std * 100:.2f}%", fontsize=80, fontweight="bold", color=STD, alpha=b)
    fig.text(0.50, 0.55, f"standard 3-bit first layer (PyMatching: {D['mwpm'] * 100:.2f}%)", fontsize=24,
             color=INK2, alpha=b)
    c = ease(t, 3.2)
    fig.text(0.07, 0.38, "Why: every first-layer neuron needs finer detector weights.", fontsize=27, color=INK,
             alpha=c)
    fig.text(0.07, 0.33, "A few extra side neurons can't make up for that.", fontsize=27, color=INK, alpha=c)
    d = ease(t, 5.5)
    fig.text(0.07, 0.15, "Next: all four designs, live on the FPGA  →", fontsize=32, fontweight="bold",
             color=STD, alpha=d)


SCENES = [(s_title, 5), (s_problem, 8), (s_ideas, 9), (s_fair, 8), (s_result1, 12), (s_knockout, 10),
          (s_learned, 10), (s_cost, 11), (s_verdict, 11)]


def render(scenes, out: Path, V):
    fig = plt.figure(figsize=(W, H), dpi=DPI, facecolor=SURFACE)
    writer = imageio_ffmpeg.write_frames(str(out), (W * DPI, H * DPI), fps=FPS, quality=8, macro_block_size=8)
    writer.send(None)
    for si, (fn, dur) in enumerate(scenes):
        nf = int(dur * FPS)
        for f in range(nf):
            t = f / FPS
            fig.clf()
            fig.set_facecolor(SURFACE)
            fn(fig, t, V)
            last = si == len(scenes) - 1  # hold the final frame (end screen / thumbnail), no fade-out
            fade = min(ease(t, 0, 0.4), 1 if last else 1 - ease(t, dur - 0.4, 0.4))
            if fade < 1:
                fig.add_artist(Rectangle((0, 0), 1, 1, transform=fig.transFigure, color=SURFACE, alpha=1 - fade,
                                         zorder=100))
            fig.canvas.draw()
            writer.send(np.ascontiguousarray(np.asarray(fig.canvas.buffer_rgba())[:, :, :3]))
    writer.close()
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preview", type=int, help="render one scene (1-based) to a PNG of its final frame")
    args = ap.parse_args()
    V = data()
    if args.preview:
        fn, dur = SCENES[args.preview - 1]
        fig = plt.figure(figsize=(W, H), dpi=DPI, facecolor=SURFACE)
        fn(fig, dur - 0.5, V)
        p = Path(f"results/video_scene{args.preview}.png")
        fig.savefig(p, facecolor=SURFACE)
        print("wrote", p)
        return
    render(SCENES, OUT, V)
    print(f"wrote {OUT} ({sum(d for _, d in SCENES)} s)")


if __name__ == "__main__":
    main()
