"""Portfolio media: publication-style figures + a one-page PDF summary, all generated from
the project's own result files (no screenshots needed).

  python host/make_figures.py            -> portfolio/*.png (300 dpi), portfolio/*.svg, portfolio/summary.pdf

Sources: data/baseline_d3_r3.json, results/study.jsonl, results/nexp.jsonl (if present),
build/<model>/hil_result.json + net.json, build/fpga/reports/utilization.rpt + timing.rpt,
results/sim_tb_engine.log, results/sim_tb_top.log.
"""

import json
import re
import textwrap
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

MODEL = Path("build/exp_d3_r3_p0.005_s5_k3_awq_L0n24")
OUT = Path("portfolio")
N_DET = 24

# Reference palette (dataviz skill, light mode): categorical slots in fixed order + text/surface tokens
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8b8a85", "#e4e3df", "#fcfcfb"
NEUTRAL = "#b9b8b2"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.titlecolor": INK, "axes.titleweight": "bold",
    "axes.titlesize": 12, "axes.titlelocation": "left", "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "lines.linewidth": 2, "lines.markersize": 7,
})


# ----------------------------------------------------------------------------- data

def load_jsonl(p: Path):
    if not p.exists():
        return []
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    return list({r["name"]: r for r in rows}.values())


def xnor_bits(r) -> int:
    if "xnor_bits" in r:
        return r["xnor_bits"]
    dims = [r["n_in"]] + r["hidden"] + [1]
    k = r.get("k", 1)
    sal = r.get("salient_channels") or [[] for _ in range(len(dims) - 1)]
    return sum(dims[i + 1] * (dims[i] + (k - 1) * len(sal[i])) for i in range(len(dims) - 1))


def ms(v):
    a = np.array(v, float)
    return a.mean(), (a.std(ddof=1) if len(a) > 1 else 0.0)


def gather():
    base = json.loads(Path("data/baseline_d3_r3.json").read_text())
    b005 = next(r for r in base["results"] if abs(r["p"] - 0.005) < 1e-12)
    study = load_jsonl(Path("results/study.jsonl"))
    fp = {r["hidden"][0]: r["test_ler"] for r in study if r["model"] == "fp"}
    bnn, l0w, A = defaultdict(list), defaultdict(list), defaultdict(list)
    bits = {}
    for r in study:
        w = r["hidden"][0]
        if r["model"] == "bnn":
            bnn[w].append(r["test_ler"])
            bits[("bnn", w)] = xnor_bits(r)
        elif r["model"] == "expanded":
            sl = r.get("salient_layers") or []
            n0 = len(r["salient_channels"][0])
            if sl and sl[1] == 0 and sl[2] == 0 and r["k"] == 3:
                if w == 128:
                    A[(r["saliency"] if n0 != N_DET else "all", n0)].append(r["test_ler"])
                if n0 == N_DET:
                    l0w[w].append(r["test_ler"])
                    bits[("l0", w)] = xnor_bits(r)
    hil = json.loads((MODEL / "hil_result.json").read_text())
    net = json.loads((MODEL / "net.json").read_text())
    util = Path("build/fpga/reports/utilization.rpt").read_text()

    def used(label):
        # | Site Type | Used | Fixed | Prohibited | Available | Util% |  -> (used, available)
        m = re.search(rf"\|\s*{re.escape(label)}\s*\|\s*([\d.]+)\s*\|\s*\d+\s*\|\s*\d+\s*\|\s*(\d+)\s*\|", util)
        return float(m.group(1)), float(m.group(2))

    res = {k: used(lbl) for k, lbl in (("LUTs", "Slice LUTs"), ("Flip-flops", "Slice Registers"),
                                       ("Block RAM", "Block RAM Tile"), ("DSP slices", "DSPs"))}
    wns = float(re.search(r"WNS\(ns\).*?\n.*?\n\s*(-?[\d.]+)", Path("build/fpga/reports/timing.rpt").read_text(),
                          re.S).group(1))
    sim_e = re.search(r"(\d+) vectors, (\d+) mismatches.*?(\d+) cycles", Path("results/sim_tb_engine.log").read_text("utf-8-sig"))
    sim_t = Path("results/sim_tb_top.log").read_text("utf-8-sig")
    sim_t_load = re.search(r"(\d+) acks, (\d+) error", sim_t)
    sim_t_inf = re.search(r"(\d+) infer frames, (\d+) replies, (\d+) mismatches", sim_t)
    nexp = load_jsonl(Path("results/nexp.jsonl"))
    return dict(trivial=b005["trivial_ler"], mwpm=b005["pymatching_ler"], fp=fp, bnn=bnn, l0w=l0w, A=A,
                bits=bits, hil=hil, net=net, res=res, wns=wns, sim_e=sim_e, sim_t_load=sim_t_load,
                sim_t_inf=sim_t_inf, nexp=nexp)


# ----------------------------------------------------------------------------- figures

def fig_headline(D, ax=None):
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(7.5, 3.6))
    bnn_m, bnn_s = ms(D["bnn"][128])
    rows = [("Plain binary network (128 wide)", bnn_m, bnn_s, NEUTRAL),
            ("PyMatching (standard decoder)", D["mwpm"], 0, NEUTRAL),
            ("Full-precision network (teacher)", D["fp"][128], 0, NEUTRAL),
            ("This project, running on the FPGA", D["hil"]["fpga_ler"], 0, BLUE)]
    y = np.arange(len(rows))[::-1]
    for yi, (lab, v, s, c) in zip(y, rows):
        ax.barh(yi, v, height=0.62, color=c, xerr=s if s else None,
                error_kw=dict(ecolor=INK2, capsize=3, lw=1))
        ax.text(v + max(s, 0) + 0.0004, yi, f"{v * 100:.2f}%", va="center", color=INK, fontsize=10,
                fontweight="bold" if c == BLUE else "normal")
    ax.set_yticks(y, [r[0] for r in rows])
    ax.set_xlim(0, max(r[1] + r[2] for r in rows) * 1.18)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=1))
    ax.set_xlabel("logical error rate (lower is better)")
    ax.grid(axis="y", visible=False)
    if own:
        fig.suptitle("Decoding accuracy, distance-3 surface code, physical error rate 0.5%", x=0.01, ha="left",
                     fontweight="bold", fontsize=12, color=INK)
        h = D["hil"]
        fig.text(0.01, 0.01, f"FPGA result: {h['shots']:,} test shots, {h['mismatches_vs_golden']} mismatches vs the "
                 f"bit-exact golden model. Plain-network bar: mean ± std over {len(D['bnn'][128])} seeds.",
                 fontsize=7.5, color=INK2)
        fig.tight_layout(rect=(0, 0.04, 1, 1))
        return fig


def fig_saliency(D):
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    bnn_m, bnn_s = ms(D["bnn"][128])
    all_m, all_s = ms(D["A"][("all", N_DET)])
    series = [("awq", "AWQ ranking (this project)", BLUE, "o"), ("random", "random choice", ORANGE, "s"),
              ("wanda", "Wanda ranking", AQUA, "D"), ("inverse", "inverse ranking", YELLOW, "v")]
    for key, lab, c, mk in series:
        ns = sorted(n for (m, n) in D["A"] if m == key)
        pts = [(0, bnn_m, bnn_s)] + [(n, *ms(D["A"][(key, n)])) for n in ns] + [(N_DET, all_m, all_s)]
        x, y, e = map(np.array, zip(*pts))
        ax.plot(x, y, color=c, marker=mk, label=lab, zorder=3 if key == "awq" else 2,
                markeredgecolor=SURFACE, markeredgewidth=1.5)
        ax.fill_between(x, y - e, y + e, color=c, alpha=0.12, lw=0)
    ax.axhline(D["mwpm"], color=INK2, ls=(0, (2, 2)), lw=1.2)
    ax.text(24.3, D["mwpm"], "PyMatching", va="center", fontsize=8, color=INK2)
    ax.axhline(D["fp"][128], color=MUTED, ls=(0, (1, 2)), lw=1.2)
    ax.text(24.3, D["fp"][128], "full precision", va="center", fontsize=8, color=MUTED)
    ax.set_xlim(-0.5, 27.5)
    ax.set_xticks([0, 1, 2, 3, 6, 12, 24])
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=1))
    ax.set_xlabel("first-layer detectors given 3-bit weights (of 24)")
    ax.set_ylabel("logical error rate")
    ax.set_title("Which detectors deserve extra precision?")
    ax.legend(loc="upper right", fontsize=8.5)
    n_seeds = min(len(v) for v in D["A"].values())
    fig.text(0.01, 0.01, f"Binary network 128-128, mean over ≥{n_seeds} seeds, band = ±1 std. "
             "0 = plain binary network, 24 = whole first layer 3-bit.", fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    return fig


def fig_pareto(D, ax=None):
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(7.5, 4.4))
    for key, src, lab, c, mk in (("bnn", D["bnn"], "plain binary network (made wider)", ORANGE, "s"),
                                 ("l0", D["l0w"], "3-bit first layer (this project)", BLUE, "o")):
        pts = sorted((D["bits"][(key, w)], *ms(src[w]), w) for w in src if (key, w) in D["bits"])
        x, y, e, ws = zip(*pts)
        ax.errorbar(x, y, yerr=e, color=c, marker=mk, label=lab, capsize=3, markeredgecolor=SURFACE,
                    markeredgewidth=1.5, elinewidth=1)
        for xi, yi, wi in zip(x, y, ws):
            ax.annotate(f"{wi} wide", (xi, yi), textcoords="offset points", xytext=(6, 5), fontsize=7.5, color=INK2)
    ax.axhline(D["mwpm"], color=INK2, ls=(0, (2, 2)), lw=1.2)
    ax.text(ax.get_xlim()[0] * 1.05 if not own else 3000, D["mwpm"] * 0.985, "PyMatching", fontsize=8,
            color=INK2, va="top")
    ax.set_xscale("log")
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=1))
    ax.set_xlabel("hardware cost: XNOR bits per decode (log scale)")
    ax.set_ylabel("logical error rate")
    ax.set_title("Accuracy vs hardware cost")
    ax.legend(loc="upper right", fontsize=8.5)
    if own:
        fig.text(0.01, 0.01, "Each point: mean ± std over 5 seeds. Lower-left is better.", fontsize=7.5, color=INK2)
        fig.tight_layout(rect=(0, 0.04, 1, 1))
        return fig


def fig_resources(D, ax=None):
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(7.5, 2.8))
    names = list(D["res"])[::-1]
    for i, k in enumerate(names):
        u, avail = D["res"][k]
        pct = 100 * u / avail
        ax.barh(i, 100, height=0.6, color=GRID)
        ax.barh(i, max(pct, 0.4), height=0.6, color=BLUE)
        used_s = f"{u:,.1f}" if u % 1 else f"{u:,.0f}"
        ax.text(max(pct, 0.4) + 1.5, i, f"{pct:.1f}%  ({used_s} of {avail:,.0f})", va="center", fontsize=9, color=INK)
    ax.set_yticks(range(len(names)), names)
    ax.set_xlim(0, 100)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(100))
    ax.grid(axis="y", visible=False)
    ax.set_title("FPGA resources used (Spartan-7 XC7S25)")
    if own:
        fig.text(0.01, 0.015, f"Vivado 2026.1 post-route utilization. Timing met at 12 MHz with "
                 f"{D['wns']:.1f} ns slack.", fontsize=7.5, color=INK2)
        fig.tight_layout(rect=(0, 0.08, 1, 1))
        return fig


def fig_verification(D, ax=None):
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(9, 2.6))
    ax.set_axis_off()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 2.6)
    e, tl, ti, h, net = D["sim_e"], D["sim_t_load"], D["sim_t_inf"], D["hil"], D["net"]
    stages = [("Trained\nnetwork", "PyTorch", "reference"),
              ("Integer\ngolden model", f"{net['test_shots']:,} shots", f"{net['golden_vs_pytorch_mismatches']} mismatches"),
              ("Chip logic,\nsimulated", f"{int(e.group(1)):,} test vectors", f"{e.group(2)} mismatches"),
              ("Full system,\nsimulated", f"{tl.group(1)} load commands +\n{ti.group(1)} decodes over UART",
               f"{ti.group(3)} mismatches"),
              ("Real FPGA\nboard", f"{h['shots']:,} shots", f"{h['mismatches_vs_golden']} mismatches")]
    w, gap = 1.72, 0.3
    for i, (t, sub, res) in enumerate(stages):
        x0 = 0.05 + i * (w + gap)
        last = i == len(stages) - 1
        ax.add_patch(FancyBboxPatch((x0, 0.35), w, 1.9, boxstyle="round,pad=0.02,rounding_size=0.12",
                                    fc=BLUE if last else "#eef3fb", ec=BLUE, lw=1.4))
        tc = SURFACE if last else INK
        ax.text(x0 + w / 2, 1.85, t, ha="center", va="center", fontsize=8.6, fontweight="bold", color=tc, wrap=True)
        ax.text(x0 + w / 2, 1.3, sub, ha="center", va="center", fontsize=7.4, color=tc, wrap=True)
        ax.text(x0 + w / 2, 0.75, res, ha="center", va="center", fontsize=8.6, color=tc,
                fontweight="bold" if i else "normal")
        if i:
            ax.add_patch(FancyArrowPatch((x0 - gap + 0.03, 1.3), (x0 - 0.03, 1.3), arrowstyle="-|>",
                                         mutation_scale=12, color=INK2, lw=1.2))
    ax.set_title("Verification chain: every stage checked bit-for-bit against the one before")
    if own:
        fig.tight_layout()
        return fig


def fig_nexp(D):
    rows = [r for r in D["nexp"]]
    if len(rows) < 6:
        return None
    groups = defaultdict(list)
    for r in rows:
        kind = "plain" if r.get("plain") else r["saliency"]
        groups[(r["schedule"], kind, r["n_sal"])].append((r["test_ler"], r["xnor_bits"]))
    fig, axes = plt.subplots(1, 2, figsize=(9, 4), sharey=True)
    for ax, sched in zip(axes, ("uniform", "tiered")):
        for kind, lab, c, mk in (("awq", "AWQ-ranked expansion", BLUE, "o"), ("random", "random detectors", ORANGE, "s"),
                                 ("plain", "same extra neurons, plain ±1", MUTED, "^")):
            ns = sorted(n for (s, k, n) in groups if s == sched and k == kind)
            if not ns:
                continue
            m = [ms([v for v, _ in groups[(sched, kind, n)]]) for n in ns]
            ax.errorbar(ns, [a for a, _ in m], yerr=[b for _, b in m], color=c, marker=mk, label=lab, capsize=3,
                        markeredgecolor=SURFACE, markeredgewidth=1.5, elinewidth=1)
        ax.axhline(D["mwpm"], color=INK2, ls=(0, (2, 2)), lw=1.2)
        ax.set_title(f"{sched} unit mix")
        ax.set_xlabel("salient detectors")
        ax.set_xticks([3, 6, 12])
    axes[0].set_ylabel("logical error rate")
    axes[0].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=1))
    axes[0].yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(0.002))
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, fontsize=8.5, bbox_to_anchor=(0.5, 0.05))
    fig.suptitle("Neuron expansion: dedicated neurons for salient detectors", x=0.01, ha="left",
                 fontweight="bold", fontsize=12)
    fig.text(0.01, 0.01, f"{len(rows)} runs, {len(rows) // len(groups)} seeds per point (mean ± std). Dashed line: PyMatching.",
             fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    return fig


# ----------------------------------------------------------------------------- one-page summary

def summary_pdf(D, path: Path):
    fig = plt.figure(figsize=(8.5, 11))
    fig.text(0.06, 0.955, "A binary neural-network decoder for quantum error\ncorrection on a small FPGA",
             fontsize=15, fontweight="bold", color=INK, va="bottom", linespacing=1.15)
    fig.text(0.06, 0.935, "Distance-3 surface code · Stim + PyTorch + Verilog · Spartan-7 XC7S25 (PLTW S7 board)",
             fontsize=9.5, color=INK2)

    h, bits = D["hil"], D["bits"]
    gain = (D["mwpm"] - h["fpga_ler"]) / D["mwpm"] * 100
    ratio = bits[("bnn", 384)] / bits[("l0", 96)]
    lut_used, lut_avail = D["res"]["LUTs"]
    tiles = [(f"{h['fpga_ler'] * 100:.2f}%", f"logical error rate\non the FPGA ({gain:.0f}%\nbelow PyMatching)"),
             (f"{h['mismatches_vs_golden']}", f"mismatches over\n{h['shots']:,}\nhardware test shots"),
             (f"{ratio:.0f}×", "fewer XNOR bits than\na plain binary network\nof similar accuracy"),
             (f"{100 * lut_used / lut_avail:.0f}%", "of the FPGA's logic\n(LUTs) used; timing\nmet at 12 MHz")]
    for i, (big, small) in enumerate(tiles):
        x = 0.06 + i * 0.225
        fig.text(x, 0.875, big, fontsize=22, fontweight="bold", color=BLUE)
        fig.text(x, 0.862, small, fontsize=8, color=INK2, va="top", linespacing=1.3)

    ax1 = fig.add_axes([0.32, 0.6, 0.62, 0.17])
    fig_headline(D, ax1)
    ax2 = fig.add_axes([0.1, 0.33, 0.84, 0.21])
    fig_pareto(D, ax2)
    ax3 = fig.add_axes([0.03, 0.08, 0.94, 0.19])
    fig_verification(D, ax3)

    notes = ("What it does: a small neural network reads 24 syndrome bits from a simulated quantum memory and predicts "
             "whether a logical error occurred. Weights and activations are binary (XNOR + popcount), except a few "
             "'salient' first-layer weights that get 3-bit precision. Choosing which detectors get the extra bits by "
             "their activity (AWQ-style) beat random choice, and expanding the first layer beat simply making the "
             "network wider by about 10× in hardware cost.")
    fig.text(0.06, 0.055, textwrap.fill(notes, 120), fontsize=7.6, color=INK2, va="top", linespacing=1.35)
    fig.savefig(path)
    fig.savefig(path.with_suffix(".png"), dpi=200)
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    D = gather()
    figs = {"1_accuracy": fig_headline(D), "2_saliency": fig_saliency(D), "3_cost_vs_accuracy": fig_pareto(D),
            "4_fpga_resources": fig_resources(D), "5_verification_chain": fig_verification(D),
            "6_neuron_expansion": fig_nexp(D)}
    for name, fig in figs.items():
        if fig is None:
            continue
        fig.savefig(OUT / f"{name}.png", dpi=300)
        fig.savefig(OUT / f"{name}.svg")
        plt.close(fig)
        print(f"wrote {OUT / name}.png/.svg")
    summary_pdf(D, OUT / "summary.pdf")
    print(f"wrote {OUT / 'summary.pdf'}")


if __name__ == "__main__":
    main()
