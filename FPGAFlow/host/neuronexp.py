"""Neuron-expansion BNN: salient layer-0 detectors get dedicated hidden neurons.

For each salient detector j (ranked like train.py: awq / inverse / wanda / random) the first
hidden layer gets extra "dedicated" neurons, one per unit in --units (default 5):

  unit "1,1"    detector-j weight = +-1 +-1        in {-2, 0, 2}
  unit "2,2"    detector-j weight = +-2 +-2        in {-4, 0, 4}
  unit "4,2,1"  detector-j weight = +-4 +-2 +-1    odd values in [-7, 7]

Every dedicated neuron sees all detectors with ordinary +-1 weights, except that detector j's
weight is the sum of binary terms above. Each has its own BN -> sign (= integer threshold in
hardware), and its output feeds the next layer as an extra input. So the network gains
nonlinear branches that weigh one salient detector at several strengths, all still
XNOR-popcount + shift-add in hardware.

Initialisation: each dedicated neuron clones the teacher neuron with the largest |weight| on
detector j (top-U distinct neurons per detector), including its downstream weights; the
detector-j terms start with the teacher weight's sign. Small noise breaks symmetry.

Per-rank schedules (--rank-units): each salient rank can get its own unit mix, e.g. the
built-in 'tiered' schedule gives rank 1 five units (wide ranges), ranks 2-3 three, and lower
ranks two narrow ones. Detectors are assigned in true rank order (score order).

Control (--plain): the same extra neurons, cloned the same way, but with ordinary +-1 weights
on every detector. It isolates "more neurons" from "graded emphasis on salient detectors".

  python host/neuronexp.py --data data/d3_r3_p0.005.npz --teacher models/study/fp_d3_r3_p0.005_w128.pt --n-sal 6
  python host/neuronexp.py ... --n-sal 6 --plain
"""

import argparse
import json
import math
import time
from pathlib import Path

import torch  # before numpy (duplicate OpenMP runtime on this machine otherwise)
import torch.nn as nn
import torch.nn.functional as F

from train import (DEVICE, BinLinear, SignSTE, Teacher, WeightSignSTE, fit, ler, load_data,
                   saliency_masks)

DEFAULT_UNITS = "1,1;1,1;2,2;2,2;4,2,1"
# Tiered: the top-ranked detector gets more, wider units; lower ranks fewer, narrower ones.
TIERED = "4,2,1;4,2,1;2,2;2,2;1,1|4,2,1;2,2;1,1|4,2,1;2,2;1,1|2,2;1,1"


def parse_units(spec: str) -> list[list[int]]:
    return [[int(v) for v in u.split(",")] for u in spec.split(";") if u]


def parse_rank_units(spec: str) -> list[list[list[int]]]:
    """'specR1|specR2|...' -> per-rank unit lists; the last one repeats for lower ranks."""
    return [parse_units(s) for s in spec.split("|") if s]


@torch.no_grad()
def ranked_salient(teacher: Teacher, calib_x, n_sal: int, method: str, seed: int) -> list[int]:
    """Salient layer-0 detectors in rank order (rank 1 first)."""
    masks, scores = saliency_masks(teacher, calib_x, [n_sal / calib_x.shape[1]] + [0] * len(teacher.fcs),
                                   method, seed)
    sal = masks[0].nonzero().flatten().tolist()
    score = scores[0]
    if method in ("awq", "wanda"):
        return sorted(sal, key=lambda j: -score[j])
    if method == "inverse":
        return sorted(sal, key=lambda j: score[j])
    g = torch.Generator().manual_seed(seed + 7)
    return [sal[i] for i in torch.randperm(len(sal), generator=g).tolist()]


class DedicatedNeurons(nn.Module):
    """D binary neurons; neuron d weighs channel chan[d] with a sum of scaled binary terms."""

    def __init__(self, n_in: int, chans: list[int], units: list[list[int]] | None):
        super().__init__()
        d = len(chans)
        self.n_in = n_in
        self.plain = units is None
        self.weight = nn.Parameter(torch.zeros(d, n_in))
        self.register_buffer("chan", torch.tensor(chans, dtype=torch.long))
        t = max((len(u) for u in units), default=1) if units else 1
        scales = torch.zeros(d, t)
        if units:
            for i, u in enumerate(units):
                scales[i, :len(u)] = torch.tensor(u, dtype=torch.float32)
        self.register_buffer("scales", scales)
        self.terms = nn.Parameter(torch.zeros(d, t))

    def int_weight(self):
        v = WeightSignSTE.apply(self.weight)
        if not self.plain:
            onehot = F.one_hot(self.chan, self.n_in).bool()
            vj = (self.scales * WeightSignSTE.apply(self.terms)).sum(1)
            v = torch.where(onehot, vj[:, None], v)
        return v

    def forward(self, x):
        return F.linear(x, self.int_weight())


class NeuronExpBNN(nn.Module):
    def __init__(self, n_in: int, hidden: list[int], chans: list[int], units: list[list[int]] | None):
        super().__init__()
        h0, d = hidden[0], len(chans)
        self.fc0 = BinLinear(n_in, h0)
        self.bn0 = nn.BatchNorm1d(h0)
        self.ded = DedicatedNeurons(n_in, chans, units)
        self.bnd = nn.BatchNorm1d(d)
        dims = [h0 + d] + hidden[1:]
        self.fcs = nn.ModuleList(BinLinear(dims[i], dims[i + 1]) for i in range(len(hidden) - 1))
        self.bns = nn.ModuleList(nn.BatchNorm1d(h) for h in hidden[1:])
        self.out = BinLinear(dims[-1], 1)
        self.out_scale = nn.Parameter(torch.tensor(1.0))
        self.out_bias = nn.Parameter(torch.tensor(0.0))

    def forward(self, x01):
        x = 2 * x01 - 1
        x = torch.cat([SignSTE.apply(self.bn0(self.fc0(x))), SignSTE.apply(self.bnd(self.ded(x)))], 1)
        for fc, bn in zip(self.fcs, self.bns):
            x = SignSTE.apply(bn(fc(x)))
        return self.out(x).squeeze(-1) * self.out_scale + self.out_bias

    @torch.no_grad()
    def init_from_teacher(self, t: Teacher, src: list[int], noise: float = 0.2):
        w0 = t.fcs[0].weight
        h0 = w0.shape[0]
        self.fc0.weight.copy_(w0)
        self.bn0.weight.copy_(t.bns[0].weight)
        self.bn0.bias.copy_(t.bns[0].bias)
        src_t = torch.tensor(src, device=w0.device)
        scale = w0.abs().mean()
        self.ded.weight.copy_(w0[src_t] + noise * scale * torch.randn_like(w0[src_t]))
        wj = w0[src_t, self.ded.chan]
        self.ded.terms.copy_(wj[:, None] + noise * scale * torch.randn_like(self.ded.terms))
        self.bnd.weight.copy_(t.bns[0].weight[src_t])
        self.bnd.bias.copy_(t.bns[0].bias[src_t])
        # next layer: original columns from the teacher, dedicated columns = their source's columns
        nxt_t = t.fcs[1] if len(t.fcs) > 1 else t.out
        nxt = self.fcs[0] if len(self.fcs) else self.out
        nxt.weight[:, :h0].copy_(nxt_t.weight)
        nxt.weight[:, h0:].copy_(nxt_t.weight[:, src_t])
        for i in range(1, len(self.fcs)):
            self.fcs[i].weight.copy_(t.fcs[i + 1].weight)
        for bb, tb in zip(self.bns, t.bns[1:]):
            bb.weight.copy_(tb.weight)
            bb.bias.copy_(tb.bias)
        if len(self.fcs):
            self.out.weight.copy_(t.out.weight)

    def xnor_bits(self) -> int:
        """Weight bits / XNOR inputs per inference (each extra binary term counts one bit)."""
        n_in = self.fc0.weight.shape[1]
        bits = self.fc0.weight.numel()
        d = self.ded.chan.numel()
        if self.ded.plain:
            bits += d * n_in
        else:
            bits += d * (n_in - 1) + int((self.ded.scales != 0).sum())
        for fc in self.fcs:
            bits += fc.weight.numel()
        return bits + self.out.weight.numel()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--teacher", type=Path, required=True)
    ap.add_argument("--hidden", type=int, nargs="+", default=[128, 128])
    ap.add_argument("--n-sal", type=int, required=True, help="number of salient layer-0 detectors")
    ap.add_argument("--saliency", choices=["awq", "inverse", "wanda", "random"], default="awq")
    ap.add_argument("--units", default=DEFAULT_UNITS, help="';'-separated units, ','-separated term scales")
    ap.add_argument("--rank-units", default=None,
                    help="per-rank unit specs separated by '|' (last repeats); 'tiered' = built-in "
                         "schedule. Overrides --units.")
    ap.add_argument("--plain", action="store_true", help="control: extra neurons with plain +-1 weights")
    ap.add_argument("--kd", type=float, default=0.5)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--bs", type=int, default=4096)
    ap.add_argument("--val-frac", type=float, default=0.05)
    ap.add_argument("--tag", default="")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", type=Path, default=Path("models"))
    ap.add_argument("--results", type=Path, default=Path("results/results.jsonl"))
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    data = load_data(args.data, args.val_frac)
    n_in = data["train"][0].shape[1]
    t0 = time.time()

    ck = torch.load(args.teacher, map_location=DEVICE)
    if ck["config"]["hidden"] != args.hidden:
        raise SystemExit(f"--hidden {args.hidden} must match teacher {ck['config']['hidden']}")
    teacher = Teacher(n_in, args.hidden).to(DEVICE)
    teacher.load_state_dict(ck["state_dict"])

    sal = ranked_salient(teacher, data["calib"][0].float(), args.n_sal, args.saliency, args.seed)
    spec = TIERED if args.rank_units == "tiered" else (args.rank_units or args.units)
    per_rank = parse_rank_units(spec)
    w0 = teacher.fcs[0].weight.abs()
    chans, src, unit_list = [], [], []
    for r, j in enumerate(sal):
        units = per_rank[min(r, len(per_rank) - 1)]
        top = torch.argsort(w0[:, j], descending=True)[:len(units)].tolist()
        for u, i in zip(units, top):
            chans.append(j)
            src.append(i)
            unit_list.append(u)

    model = NeuronExpBNN(n_in, args.hidden, chans, None if args.plain else unit_list).to(DEVICE)
    model.init_from_teacher(teacher, src)

    stem = args.data.stem
    sched = "tiered" if args.rank_units == "tiered" else ("custom" if args.rank_units else "uniform")
    name = f"nexp_{stem}_n{args.n_sal}_{args.saliency}_{sched}" + ("_plain" if args.plain else "")
    if args.tag:
        name += f"_{args.tag}"
    if args.seed:
        name += f"_seed{args.seed}"
    print(f"salient detectors by rank {sal}; {len(chans)} dedicated neurons; xnor bits {model.xnor_bits()}")
    print("units per rank:", [per_rank[min(r, len(per_rank) - 1)] for r in range(len(sal))])

    val_ler, best_ep = fit(model, data, args.epochs, args.lr, args.bs, 0.0, name, teacher=teacher, kd=args.kd)
    test_ler = ler(model, *data["test"])
    n_test = len(data["test"][1])

    config = {"model": "neuronexp", "hidden": args.hidden, "n_in": n_in, "data": str(args.data),
              "p": data["p"], "epochs": args.epochs, "lr": args.lr, "bs": args.bs, "seed": args.seed,
              "kd": args.kd, "tag": args.tag, "saliency": args.saliency, "n_sal": args.n_sal,
              "schedule": sched, "units": spec, "plain": args.plain, "n_dedicated": len(chans),
              "ranked_salient": sal}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    torch.save({"config": config, "state_dict": model.state_dict(), "chans": chans, "src": src},
               args.out_dir / f"{name}.pt")
    result = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "name": name, **config,
              "salient_channels": [sal] + [[] for _ in args.hidden], "xnor_bits": model.xnor_bits(),
              "best_epoch": best_ep, "val_ler": val_ler, "test_ler": test_ler,
              "test_ler_stderr": math.sqrt(test_ler * (1 - test_ler) / n_test),
              "mwpm_ler": data["mwpm_ler"], "train_seconds": round(time.time() - t0, 1)}
    args.results.parent.mkdir(parents=True, exist_ok=True)
    with args.results.open("a") as f:
        f.write(json.dumps(result) + "\n")
    print(f"\n{name}: test LER {test_ler:.6f} +- {result['test_ler_stderr']:.6f}  "
          f"(PyMatching {data['mwpm_ler']:.6f}, best epoch {best_ep}, {result['train_seconds']}s)")


if __name__ == "__main__":
    main()
