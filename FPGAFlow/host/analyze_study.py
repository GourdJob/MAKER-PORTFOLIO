"""Tables + figures for the main study (results/study.jsonl).

  python host/analyze_study.py            -> prints Markdown tables, writes results/figures/*.png

Figures:
  study_A_layer0.png   test LER vs number of expanded layer-0 detectors, per saliency method
  study_C_pareto.png   test LER vs XNOR bits: widening the plain BNN vs layer-0 expansion
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

N_DET = 24


def xnor_bits(r) -> int:
    dims = [r["n_in"]] + r["hidden"] + [1]
    k = r.get("k", 1)
    sal = r.get("salient_channels") or [[] for _ in range(len(dims) - 1)]
    return sum(dims[i + 1] * (dims[i] + (k - 1) * len(sal[i])) for i in range(len(dims) - 1))


def stats(vals):
    a = np.array(vals)
    return a.mean(), (a.std(ddof=1) if len(a) > 1 else 0.0), len(a)


def fmt(vals):
    m, s, n = stats(vals)
    return f"{m:.5f} ± {s:.5f} (n={n})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=Path("results/study.jsonl"))
    ap.add_argument("--figdir", type=Path, default=Path("results/figures"))
    args = ap.parse_args()
    rows = [json.loads(l) for l in args.results.read_text().splitlines() if l.strip()]
    latest = {r["name"]: r for r in rows}.values()
    args.figdir.mkdir(parents=True, exist_ok=True)

    mwpm = next(iter(latest))["mwpm_ler"]
    fp = {r["hidden"][0]: r["test_ler"] for r in latest if r["model"] == "fp"}
    bnn = defaultdict(list)          # width -> LERs
    l0 = defaultdict(list)           # (k, method, n) -> LERs  (128x128, layer 0 only)
    hid = defaultdict(list)          # (frac, method) -> LERs
    l0w = defaultdict(list)          # width -> LERs (L0 all detectors, k=3)
    bits = {}
    for r in latest:
        w = r["hidden"][0]
        if r["model"] == "bnn":
            bnn[w].append(r["test_ler"])
            bits[("bnn", w)] = xnor_bits(r)
        elif r["model"] == "expanded":
            sl = r.get("salient_layers") or []
            n0 = len(r["salient_channels"][0])
            if sl and sl[1] == 0 and sl[2] == 0:
                if w == 128:
                    l0[(r["k"], r["saliency"], n0)].append(r["test_ler"])
                if r["k"] == 3 and n0 == N_DET:
                    l0w[w].append(r["test_ler"])
                    bits[("l0", w)] = xnor_bits(r)
            elif sl:
                hid[(sl[1], r["saliency"])].append(r["test_ler"])

    print(f"PyMatching {mwpm:.5f}; FP teachers: " + ", ".join(f"w{w}={v:.5f}" for w, v in sorted(fp.items())))

    print("\n### A. Layer-0 expansion (128x128), test LER mean ± std over seeds")
    ns = sorted({key[2] for key in l0})
    methods = [(3, "awq"), (3, "wanda"), (3, "inverse"), (3, "random"), (2, "awq"), (2, "random")]
    print("| n detectors | " + " | ".join(f"k={k} {m}" for k, m in methods) + " |")
    print("|---|" + "---|" * len(methods))
    print(f"| 0 (plain BNN) | " + " | ".join(fmt(bnn[128]) if bnn[128] else "" for _ in methods) + " |")
    for n in ns:
        cells = []
        for k, m in methods:
            key = (k, m, n) if n != N_DET else (k, "awq", n)
            cells.append(fmt(l0[key]) if l0.get(key) else "")
        print(f"| {n} | " + " | ".join(cells) + " |")

    print("\n### B. Hidden-layer expansion on top of 3-bit layer 0 (128x128, k=3)")
    print(f"| hidden s | awq | random |\n|---|---|---|\n| 0 | {fmt(l0.get((3, 'awq', N_DET), [np.nan]))} | |")
    for f in sorted({key[0] for key in hid}):
        print(f"| {f:g} | {fmt(hid[(f, 'awq')]) if hid[(f, 'awq')] else ''} | "
              f"{fmt(hid[(f, 'random')]) if hid[(f, 'random')] else ''} |")

    print("\n### C. Pareto: XNOR bits vs test LER")
    print("| design | width | XNOR bits | test LER |\n|---|---|---|---|")
    for w in sorted(bnn):
        print(f"| plain BNN | {w} | {bits[('bnn', w)]} | {fmt(bnn[w])} |")
    for w in sorted(l0w):
        print(f"| L0 3-bit BNN | {w} | {bits[('l0', w)]} | {fmt(l0w[w])} |")

    # ---- figure A
    fig, ax = plt.subplots(figsize=(7, 4.5))
    styles = {"awq": "o-", "wanda": "s-", "inverse": "v-", "random": "x--"}
    for k, m in methods:
        pts = [(n, *stats(l0[(k, m if n != N_DET else "awq", n)])[:2]) for n in ns
               if l0.get((k, m if n != N_DET else "awq", n))]
        if bnn[128]:
            pts = [(0, *stats(bnn[128])[:2])] + pts
        if not pts:
            continue
        x, y, e = zip(*pts)
        ax.errorbar(x, y, yerr=e, fmt=styles[m], alpha=1.0 if k == 3 else 0.45, capsize=3,
                    label=f"k={k} {m}")
    ax.axhline(mwpm, color="k", ls=":", label="PyMatching")
    if 128 in fp:
        ax.axhline(fp[128], color="g", ls=":", label="FP teacher")
    ax.set_xlabel("expanded layer-0 detectors (of 24)")
    ax.set_ylabel("test logical error rate")
    ax.set_title("d=3, p=0.005, BNN 128x128: which detectors to expand")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(args.figdir / "study_A_layer0.png", dpi=150)

    # ---- figure C
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for key, lab, sty in (("bnn", "plain BNN (widen)", "o-"), ("l0", "layer-0 3-bit BNN", "s-")):
        src = bnn if key == "bnn" else l0w
        pts = sorted((bits[(key, w)], *stats(src[w])[:2], w) for w in src if (key, w) in bits)
        if pts:
            x, y, e, ws = zip(*pts)
            ax.errorbar(x, y, yerr=e, fmt=sty, capsize=3, label=lab)
            for xi, yi, wi in zip(x, y, ws):
                ax.annotate(str(wi), (xi, yi), textcoords="offset points", xytext=(4, 4), fontsize=7)
    ax.axhline(mwpm, color="k", ls=":", label="PyMatching")
    ax.set_xscale("log")
    ax.set_xlabel("XNOR bits per inference (log)")
    ax.set_ylabel("test logical error rate")
    ax.set_title("Accuracy vs hardware cost (labels = hidden width)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(args.figdir / "study_C_pareto.png", dpi=150)
    print(f"\nfigures written to {args.figdir}")


if __name__ == "__main__":
    main()
