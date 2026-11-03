"""Summarize results/results.jsonl into Markdown tables for the Research Log.

  python host/summarize.py --p 0.005

Cost proxy "XNOR bits" = sum over layers of n_out * (n_in + (k-1) * n_salient):
the weight bits stored and XNOR-popcount inputs evaluated per inference.
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


def xnor_bits(r) -> int:
    dims = [r["n_in"]] + r["hidden"] + [1]
    k = r.get("k", 1)
    sal = r.get("salient_channels") or [[] for _ in range(len(dims) - 1)]
    return sum(dims[i + 1] * (dims[i] + (k - 1) * len(sal[i])) for i in range(len(dims) - 1))


def label(r) -> str:
    # recipe tag = whatever the run name carries after the standard prefix (seed suffix dropped)
    base = re.sub(r"_seed\d+$", "", r["name"])
    tag = base.split(f"_p{r['p']:g}", 1)[-1].lstrip("_")
    if r["model"] == "expanded":
        tag = re.sub(r"^s[\d.]+_k\d+_(awq|random)_?", "", tag)
    tag = f" [{tag}]" if tag else ""
    if r["model"] == "fp":
        return "FP teacher" + tag
    if r["model"] == "bnn":
        return "Plain BNN" + tag
    return f"Expanded s={r['salient'] * 100:g}% k={r['k']} {r['saliency']}" + tag


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=Path("results/results.jsonl"))
    ap.add_argument("--p", type=float, required=True)
    ap.add_argument("--hidden", type=int, nargs="+", default=[128, 128])
    ap.add_argument("--fp-label", default="FP teacher", help="group used as the FP reference for gap recovered")
    ap.add_argument("--bnn-label", default="Plain BNN", help="group used as the BNN reference for gap recovered")
    args = ap.parse_args()

    rows = [json.loads(l) for l in args.results.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if abs(r["p"] - args.p) < 1e-12 and r["hidden"] == args.hidden]
    # keep the latest run per (name), then group seeds
    latest = {r["name"]: r for r in rows}
    groups = defaultdict(list)
    for r in latest.values():
        groups[label(r)].append(r)

    ap_fp, ap_bnn = args.fp_label, args.bnn_label
    fp = groups.get(ap_fp, [{}])[0].get("test_ler")
    bnn_runs = groups.get(ap_bnn, [])
    bnn = sum(r["test_ler"] for r in bnn_runs) / len(bnn_runs) if bnn_runs else None
    mwpm = rows[0]["mwpm_ler"] if rows else None

    print(f"p = {args.p}, hidden = {args.hidden}, PyMatching LER = {mwpm}")
    print("| Model | Seeds | Test LER (mean) | min / max | Gap recovered | XNOR bits | Salient ch. per layer |")
    print("|---|---|---|---|---|---|---|")
    order = sorted(groups, key=lambda g: (g != "FP teacher", g != "Plain BNN", g))
    for g in order:
        rs = groups[g]
        lers = [r["test_ler"] for r in rs]
        m = sum(lers) / len(lers)
        gap = ""
        if g.startswith("Expanded") and fp is not None and bnn is not None and bnn > fp:
            gap = f"{(bnn - m) / (bnn - fp) * 100:.0f}%"
        sal = rs[0].get("salient_channels")
        sal_s = "/".join(str(len(s)) for s in sal) if sal else ""
        bits = "" if rs[0]["model"] == "fp" else str(xnor_bits(rs[0]))
        print(f"| {g} | {len(rs)} | {m:.5f} | {min(lers):.5f} / {max(lers):.5f} | {gap} | {bits} | {sal_s} |")


if __name__ == "__main__":
    main()
