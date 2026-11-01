"""Look inside the trained neuron-expansion models: which salient-detector weights the dedicated
neurons learned, and how much accuracy is lost when the dedicated neurons are switched off.

  python host/analyze_nexp.py            (writes results/analysis_nexp.md)
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

import torch  # before numpy (duplicate OpenMP runtime on this machine otherwise)

from neuronexp import NeuronExpBNN
from train import DEVICE, SignSTE, load_data

N_EVAL = 300_000  # test shots used for the knockout


@torch.no_grad()
def ler_knockout(model, x, y, off: bool):
    """Test LER; with off=True the dedicated neurons output 0 (disconnected from the next layer)."""
    xs = 2 * x.float() - 1
    h0 = SignSTE.apply(model.bn0(model.fc0(xs)))
    hd = SignSTE.apply(model.bnd(model.ded(xs)))
    if off:
        hd = torch.zeros_like(hd)
    h = torch.cat([h0, hd], 1)
    for fc, bn in zip(model.fcs, model.bns):
        h = SignSTE.apply(bn(fc(h)))
    z = model.out(h).squeeze(-1) * model.out_scale + model.out_bias
    return ((z > 0).long() != y.long()).float().mean().item()


def main():
    rows = {}
    for line in Path("results/nexp.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            rows[r["name"]] = r
    data = load_data(Path(next(iter(rows.values()))["data"]), 0.05)
    x, y = data["test"][0][:N_EVAL].to(DEVICE), data["test"][1][:N_EVAL].to(DEVICE)

    knock = defaultdict(list)       # (schedule, variant, n) -> [(ler_on, ler_off)]
    values = defaultdict(Counter)   # unit type -> Counter of learned salient weights
    for name, r in sorted(rows.items()):
        ck = torch.load(Path("models/nexp") / f"{name}.pt", map_location=DEVICE)
        cfg = ck["config"]
        sd = ck["state_dict"]
        units = None
        if not cfg["plain"]:
            scales = sd["ded.scales"]
            units = [[int(v) for v in row if v != 0] for row in scales.tolist()]
        model = NeuronExpBNN(cfg["n_in"], cfg["hidden"], ck["chans"], units).to(DEVICE)
        model.load_state_dict(sd)
        model.eval()
        variant = "plain" if cfg["plain"] else cfg["saliency"]
        key = (cfg["schedule"], variant, cfg["n_sal"])
        knock[key].append((ler_knockout(model, x, y, False), ler_knockout(model, x, y, True)))
        if units:
            vj = (model.ded.scales * torch.sign(model.ded.terms)).sum(1).round().long().tolist()
            for u, v in zip(units, vj):
                values["±" + "±".join(map(str, u))][v] += 1

    out = ["# Neuron-expansion: inside the trained models", "",
           f"Knockout on the first {N_EVAL:,} test shots: dedicated neurons' outputs set to 0.", "",
           "| schedule | variant | salient n | LER (normal) | LER (dedicated off) | relative change |",
           "|---|---|---|---|---|---|"]
    for key in sorted(knock):
        on = sum(a for a, _ in knock[key]) / len(knock[key])
        off = sum(b for _, b in knock[key]) / len(knock[key])
        out.append(f"| {key[0]} | {key[1]} | {key[2]} | {on:.5f} | {off:.5f} | {100 * (off / on - 1):+.0f}% |")
    out += ["", "Learned weight on the salient detector, by unit type (all non-plain models):", "",
            "| unit | range | learned value: count |", "|---|---|---|"]
    for u, c in sorted(values.items()):
        tot = sum(c.values())
        dist = ", ".join(f"{v:+d}: {n} ({100 * n / tot:.0f}%)" for v, n in sorted(c.items()))
        rng = sum(int(t) for t in u.strip("±").split("±"))
        out.append(f"| {u} | ±{rng} | {dist} |")
    Path("results/analysis_nexp.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
