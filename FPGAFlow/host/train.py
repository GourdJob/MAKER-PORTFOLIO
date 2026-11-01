"""Phase 2: train the FP teacher, plain BNN, and saliency-expanded BNN decoders.

Models (all predict the logical observable flip from detector bits):
  fp        Full-precision teacher: Linear -> BN -> Hardtanh per hidden layer, 0/1 inputs.
  bnn       Plain BNN: +-1 weights and activations (XNOR-popcount), BN+sign folds to an
            integer threshold per neuron in hardware.
  expanded  BNN where the top-s fraction of *input channels* of every layer (ranked by the
            teacher's mean |activation| on the calibration split, AWQ-style) get k-bit
            weights instead of 1-bit.

Expanded weight scheme (integer units, per layer):
  non-salient weight  v = 2^(k-1) * b0                    (b0 in {-1,+1})
  salient weight      v in {+-1, +-3, ..., +-(2^k - 1)}   = sum_i 2^(k-1-i) * b_i
so every salient weight is exactly k binary planes combined by shifts. In hardware the
pre-activation is  z = sum_i 2^(k-1-i) * xnor_popcount(plane_i, x)  restricted per plane.
k=1 reduces to the plain BNN.

BNN and expanded models are initialised from the teacher's weights, so teacher channel j
and BNN channel j refer to the same feature, which makes teacher-ranked saliency meaningful.

Examples:
  python host/train.py --data data/d3_r3_p0.005.npz --model fp
  python host/train.py --data data/d3_r3_p0.005.npz --model bnn
  python host/train.py --data data/d3_r3_p0.005.npz --model expanded --salient 0.05 --k 2
  python host/train.py --data data/d3_r3_p0.005.npz --model expanded --salient 0.05 --k 2 --saliency random
"""

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ----------------------------------------------------------------------------- data

def load_data(path: Path, val_frac: float):
    d = np.load(path)
    # kept as uint8 on the GPU (4x smaller than float32); batches are cast in fit()/ler()
    to_t = lambda a: torch.from_numpy(a.astype(np.uint8)).to(DEVICE)
    x, y = to_t(d["train_x"]), to_t(d["train_y"][:, 0])
    n_val = int(len(x) * val_frac)
    return {
        "train": (x[n_val:], y[n_val:]),
        "val": (x[:n_val], y[:n_val]),
        "calib": (to_t(d["calib_x"]), to_t(d["calib_y"][:, 0])),
        "test": (to_t(d["test_x"]), to_t(d["test_y"][:, 0])),
        "mwpm_ler": float(np.mean(np.any(d["mwpm_test_pred"] != d["test_y"], axis=1))),
        "p": float(d["p"]),
    }


# ----------------------------------------------------------------------------- models

class Teacher(nn.Module):
    def __init__(self, n_in: int, hidden: list[int]):
        super().__init__()
        dims = [n_in] + hidden
        self.fcs = nn.ModuleList(nn.Linear(dims[i], dims[i + 1]) for i in range(len(hidden)))
        self.bns = nn.ModuleList(nn.BatchNorm1d(h) for h in hidden)
        self.out = nn.Linear(dims[-1], 1)

    def forward(self, x, return_acts: bool = False):
        acts = []  # acts[l] = input to layer l (last entry = input to output layer)
        for fc, bn in zip(self.fcs, self.bns):
            acts.append(x)
            x = F.hardtanh(bn(fc(x)))
        acts.append(x)
        logit = self.out(x).squeeze(-1)
        return (logit, acts) if return_acts else logit


class SignSTE(torch.autograd.Function):
    """sign with sign(0) = +1 (matches hardware), straight-through gradient in [-1, 1]."""

    @staticmethod
    def forward(ctx, x):
        ctx.save_for_backward(x)
        return torch.where(x >= 0, 1.0, -1.0).to(x.dtype)

    @staticmethod
    def backward(ctx, g):
        (x,) = ctx.saved_tensors
        return g * (x.abs() <= 1).to(g.dtype)


class WeightSignSTE(torch.autograd.Function):
    """sign for latent weights: identity gradient (BinaryConnect). A [-1, 1] gradient window
    here permanently freezes any weight that drifts past +-1 (measured: 56-70% frozen)."""

    @staticmethod
    def forward(ctx, w):
        return torch.where(w >= 0, 1.0, -1.0).to(w.dtype)

    @staticmethod
    def backward(ctx, g):
        return g


def round_ste(x):
    return x + (x.round() - x).detach()


def clamp_ste(x, lo, hi):
    """clamp in the forward pass, identity gradient (so saturated weights can come back)."""
    return x + (x.clamp(lo, hi) - x).detach()


class BinLinear(nn.Module):
    """Linear layer with binary (or k-bit on salient input channels) integer weights."""

    def __init__(self, n_in: int, n_out: int, k: int = 1, mask: torch.Tensor | None = None):
        super().__init__()
        self.weight = nn.Parameter(torch.randn(n_out, n_in) * 0.1)
        self.k = k
        self.register_buffer("mask", mask if mask is not None else torch.zeros(n_in, dtype=torch.bool))

    def int_weight(self):
        """Return (v, u): integer-valued weights v (as float, with STE) and the unit scale u."""
        w, k, top = self.weight, self.k, 2 ** (self.k - 1)
        nonsal = ~self.mask
        ref = w[:, nonsal] if nonsal.any() else w
        u = (ref.abs().mean() / top).detach().clamp_min(1e-8)
        v = top * WeightSignSTE.apply(w)
        if k > 1 and self.mask.any():
            # nearest odd integer in [-(2^k-1), 2^k-1]:  v = 2q+1, q in [-top, top-1]
            q = round_ste(clamp_ste((w / u - 1) / 2, -top, top - 1))
            v = torch.where(self.mask[None, :], 2 * q + 1, v)
        return v, u

    def forward(self, x):
        v, u = self.int_weight()
        return F.linear(x, v) * u


class BNN(nn.Module):
    def __init__(self, n_in: int, hidden: list[int], k: int = 1, masks: list[torch.Tensor] | None = None):
        super().__init__()
        dims = [n_in] + hidden
        masks = masks or [None] * (len(hidden) + 1)
        self.fcs = nn.ModuleList(BinLinear(dims[i], dims[i + 1], k, masks[i]) for i in range(len(hidden)))
        self.bns = nn.ModuleList(nn.BatchNorm1d(h) for h in hidden)
        self.out = BinLinear(dims[-1], 1, k, masks[-1])
        self.out_scale = nn.Parameter(torch.tensor(1.0))
        self.out_bias = nn.Parameter(torch.tensor(0.0))

    def forward(self, x01):
        x = 2 * x01 - 1  # detector bit 0/1 -> -1/+1
        for fc, bn in zip(self.fcs, self.bns):
            x = SignSTE.apply(bn(fc(x)))
        return self.out(x).squeeze(-1) * self.out_scale + self.out_bias

    @torch.no_grad()
    def init_from_teacher(self, t: Teacher):
        for bfc, tfc in zip(self.fcs, t.fcs):
            bfc.weight.copy_(tfc.weight)
        for bbn, tbn in zip(self.bns, t.bns):
            bbn.weight.copy_(tbn.weight)
            bbn.bias.copy_(tbn.bias)
        self.out.weight.copy_(t.out.weight)


# ----------------------------------------------------------------------------- saliency

@torch.no_grad()
def saliency_masks(teacher: Teacher, calib_x, frac: float | list[float], method: str, seed: int):
    """Per-layer boolean masks over input channels.

    awq      top channels by teacher mean |activation| (AWQ)
    inverse  bottom channels by the same score (ablation)
    wanda    top channels by mean |activation| * L2 norm of the teacher's weight column
    random   uniformly random channels (ablation; differs per seed)
    """
    teacher.eval()
    _, acts = teacher(calib_x, return_acts=True)
    weights = [fc.weight for fc in teacher.fcs] + [teacher.out.weight]
    gen = torch.Generator().manual_seed(seed)
    masks, scores = [], []
    fracs = frac if isinstance(frac, list) else [frac] * len(acts)
    for a, w, f in zip(acts, weights, fracs):
        n = a.shape[1]
        n_sal = 0 if f <= 0 else max(1, round(f * n))
        score = a.abs().mean(0)
        if method == "wanda":
            score = score * w.norm(dim=0)
        if method in ("awq", "wanda"):
            idx = torch.argsort(score, descending=True)[:n_sal]
        elif method == "inverse":
            idx = torch.argsort(score, descending=False)[:n_sal]
        elif method == "random":
            idx = torch.randperm(n, generator=gen)[:n_sal].to(a.device)
        else:
            raise ValueError(method)
        m = torch.zeros(n, dtype=torch.bool, device=a.device)
        m[idx] = True
        masks.append(m)
        scores.append(score.cpu().tolist())
    return masks, scores


# ----------------------------------------------------------------------------- train / eval

@torch.no_grad()
def ler(model, x, y, bs: int = 65536) -> float:
    model.eval()
    wrong = 0
    for i in range(0, len(x), bs):
        pred = (model(x[i:i + bs].float()) >= 0).to(torch.uint8)
        wrong += (pred != y[i:i + bs]).sum().item()
    return wrong / len(x)


def fit(model, data, epochs: int, lr: float, bs: int, wd: float, log_prefix: str, clip: bool = False,
        teacher: nn.Module | None = None, kd: float = 0.0):
    """kd > 0: loss = (1-kd) * BCE(labels) + kd * BCE(teacher's soft probabilities)."""
    x, y = data["train"]
    if kd > 0:
        teacher.eval()
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=wd)
    steps = epochs * math.ceil(len(x) / bs)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps, pct_start=0.1)
    best = (float("inf"), None, -1)
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(len(x), device=DEVICE)
        tot = 0.0
        for i in range(0, len(x), bs):
            idx = perm[i:i + bs]
            xb = x[idx].float()
            logit = model(xb)
            loss = F.binary_cross_entropy_with_logits(logit, y[idx].float())
            if kd > 0:
                with torch.no_grad():
                    soft = torch.sigmoid(teacher(xb))
                loss = (1 - kd) * loss + kd * F.binary_cross_entropy_with_logits(logit, soft)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
            if clip:  # BinaryNet-style latent clipping (measured worse here; off by default)
                with torch.no_grad():
                    for m in model.modules():
                        if isinstance(m, BinLinear):
                            m.weight.clamp_(-1, 1)
            tot += loss.item() * len(idx)
        v = ler(model, *data["val"])
        if v < best[0]:
            best = (v, {k: t.detach().clone() for k, t in model.state_dict().items()}, ep)
        print(f"{log_prefix} epoch {ep + 1:>3}/{epochs}  loss {tot / len(x):.5f}  val LER {v:.6f}")
    model.load_state_dict(best[1])
    return best[0], best[2] + 1


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--model", choices=["fp", "bnn", "expanded"], required=True)
    ap.add_argument("--hidden", type=int, nargs="+", default=[128, 128])
    ap.add_argument("--teacher", type=Path, help="teacher checkpoint (default: models/fp_<data>.pt)")
    ap.add_argument("--salient", type=float, default=0.05, help="fraction of input channels per layer")
    ap.add_argument("--k", type=int, default=2, help="binary terms per salient weight")
    ap.add_argument("--saliency", choices=["awq", "inverse", "wanda", "random"], default="awq")
    ap.add_argument("--epochs", type=int, default=None, help="default: 20 fp, 60 bnn/expanded")
    ap.add_argument("--lr", type=float, default=None, help="default: 3e-3 for all models")
    ap.add_argument("--bs", type=int, default=4096)
    ap.add_argument("--val-frac", type=float, default=0.05)
    ap.add_argument("--clip", action="store_true", help="clip latent binary weights to [-1, 1]")
    ap.add_argument("--kd", type=float, default=0.0, help="distillation weight on the teacher's soft labels")
    ap.add_argument("--wd", type=float, default=0.0, help="weight decay for bnn/expanded latent weights")
    ap.add_argument("--salient-layers", type=float, nargs="+", default=None,
                    help="per-layer salient fractions (overrides --salient), e.g. 1 0 0 = layer 0 only")
    ap.add_argument("--tag", default="", help="suffix for the run name (e.g. recipe variant)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", type=Path, default=Path("models"))
    ap.add_argument("--results", type=Path, default=Path("results/results.jsonl"))
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    stem = args.data.stem
    data = load_data(args.data, args.val_frac)
    n_in = data["train"][0].shape[1]
    t0 = time.time()

    extra = {}
    if args.model == "fp":
        model = Teacher(n_in, args.hidden).to(DEVICE)
        name = f"fp_{stem}"
        epochs, lr, wd = args.epochs or 20, args.lr or 3e-3, 1e-5
    else:
        tpath = args.teacher or args.out_dir / f"fp_{stem}.pt"
        ck = torch.load(tpath, map_location=DEVICE)
        teacher = Teacher(n_in, ck["config"]["hidden"]).to(DEVICE)
        teacher.load_state_dict(ck["state_dict"])
        if ck["config"]["hidden"] != args.hidden:
            raise SystemExit(f"--hidden {args.hidden} must match teacher {ck['config']['hidden']}")
        if args.model == "bnn":
            k, masks, scores = 1, None, None
            name = f"bnn_{stem}"
        else:
            k = args.k
            frac = args.salient_layers or args.salient
            if args.salient_layers and len(args.salient_layers) != len(args.hidden) + 1:
                raise SystemExit(f"--salient-layers needs {len(args.hidden) + 1} values (one per layer)")
            masks, scores = saliency_masks(teacher, data["calib"][0].float(), frac, args.saliency, args.seed)
            name = f"exp_{stem}_s{args.salient * 100:g}_k{k}_{args.saliency}"
            extra = {"salient_channels": [m.nonzero().flatten().tolist() for m in masks],
                     "saliency_scores": scores}
            print("salient channels per layer:", extra["salient_channels"])
        model = BNN(n_in, args.hidden, k, masks).to(DEVICE)
        model.init_from_teacher(teacher)
        epochs, lr, wd = args.epochs or 60, args.lr or 3e-3, args.wd

    if args.tag:
        name += f"_{args.tag}"
    if args.seed:
        name += f"_seed{args.seed}"
    val_ler, best_ep = fit(model, data, epochs, lr, args.bs, wd, name, clip=args.clip,
                           teacher=teacher if args.model != "fp" else None, kd=args.kd)
    test_ler = ler(model, *data["test"])
    n_test = len(data["test"][1])

    config = {"model": args.model, "hidden": args.hidden, "n_in": n_in, "data": str(args.data),
              "p": data["p"], "epochs": epochs, "lr": lr, "bs": args.bs, "seed": args.seed,
              "kd": args.kd, "clip": args.clip, "tag": args.tag, "weight_ste": "identity"}
    if args.model == "expanded":
        config.update(k=args.k, salient=args.salient, saliency=args.saliency,
                      salient_layers=args.salient_layers)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    torch.save({"config": config, "state_dict": model.state_dict(), **extra}, args.out_dir / f"{name}.pt")

    result = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "name": name, **config,
              "best_epoch": best_ep, "val_ler": val_ler, "test_ler": test_ler,
              "test_ler_stderr": math.sqrt(test_ler * (1 - test_ler) / n_test),
              "mwpm_ler": data["mwpm_ler"], "train_seconds": round(time.time() - t0, 1)}
    if "salient_channels" in extra:
        result["salient_channels"] = extra["salient_channels"]
    args.results.parent.mkdir(parents=True, exist_ok=True)
    with args.results.open("a") as f:
        f.write(json.dumps(result) + "\n")

    print(f"\n{name}: test LER {test_ler:.6f} +- {result['test_ler_stderr']:.6f}  "
          f"(PyMatching {data['mwpm_ler']:.6f}, best epoch {best_ep}, {result['train_seconds']}s)")


if __name__ == "__main__":
    main()
