"""Phase 3: bit-exact integer golden model of the hardware BNN.

Converts a trained bnn/expanded checkpoint into exactly what the FPGA computes:

  per layer:  planes[i] in {0,1}^(n_out x n_in)   bit 1 = weight +1, bit 0 = weight -1
              mask      in {0,1}^n_in             salient input channels (planes i >= 1 only)
              thr       int per neuron            neuron fires (+1 / bit 1) iff z >= thr

  z = sum_i 2^(k-1-i) * (2 * popcount(XNOR(plane_i, x) & S_i) - |S_i|)
      S_0 = all channels, S_i = salient channels for i >= 1

BatchNorm + sign is folded into thr. A negative BN gain is folded in by inverting that
neuron's weight bits, so hardware only ever needs "z >= thr". The output layer works the
same way; its single output bit is the predicted observable flip.

Usage:
  python host/golden.py models/bnn_d3_r3_p0.005.pt
      -> golden test LER, mismatches vs the PyTorch model, hardware cost summary
"""

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import torch  # must load before numpy's BLAS on Windows (duplicate libiomp5md.dll otherwise)
import numpy as np

from train import BNN, DEVICE


@dataclass
class GoldenLayer:
    planes: np.ndarray  # uint8 [k, n_out, n_in]
    mask: np.ndarray    # bool [n_in]
    thr: np.ndarray     # int64 [n_out]
    k: int

    @property
    def coeffs(self):
        return [2 ** (self.k - 1 - i) for i in range(self.k)]

    def int_weights(self) -> np.ndarray:
        """Reconstruct integer weights from the bit planes (planes >= 1 masked to salient)."""
        pm = np.where(self.planes == 1, 1, -1).astype(np.int64)
        v = self.coeffs[0] * pm[0]
        for i in range(1, self.k):
            v = v + self.coeffs[i] * pm[i] * self.mask[None, :]
        return v

    def preact(self, x_pm: np.ndarray) -> np.ndarray:
        """z for +-1 inputs, computed plane by plane exactly as the hardware does."""
        z = np.zeros((x_pm.shape[0], self.planes.shape[1]), dtype=np.int64)
        for i, c in enumerate(self.coeffs):
            sel = np.ones_like(self.mask) if i == 0 else self.mask
            if not sel.any():
                continue
            b = torch.from_numpy(np.where(self.planes[i][:, sel] == 1, 1.0, -1.0)).to(DEVICE)
            xs = torch.from_numpy(np.ascontiguousarray(x_pm[:, sel], dtype=np.float64)).to(DEVICE)
            # float64 sums of +-1 are exact (|sum| << 2^53). torch, not numpy, does the matmul:
            # numpy's MKL BLAS + torch load two OpenMP runtimes in this environment and abort.
            z += c * torch.round(xs @ b.T).long().cpu().numpy()
        return z


def decompose(v: np.ndarray, k: int, mask: np.ndarray) -> np.ndarray:
    """Integer weights -> k bit planes. Salient v is odd in [-(2^k-1), 2^k-1]; others +-2^(k-1)."""
    planes = np.zeros((k,) + v.shape, dtype=np.uint8)
    r = v.astype(np.int64).copy()
    for i in range(k):
        c = 2 ** (k - 1 - i)
        b = np.where(r > 0, 1, -1)
        if i > 0:
            b = np.where(mask[None, :], b, 1)  # unused plane bits: don't-care, store 1
            r = r - c * b * mask[None, :]
        else:
            r = r - c * b
        planes[i] = (b > 0).astype(np.uint8)
    if np.any(r != 0):
        raise ValueError("weights not representable with k planes")
    return planes


def _fold_threshold(v: np.ndarray, a: np.ndarray, b: np.ndarray):
    """Neuron fires iff a*z + b >= 0. Return (v', thr) with fire iff z' >= thr, z' = v'.x.

    a > 0: z >= -b/a           -> thr = ceil(-b/a)
    a < 0: z <= -b/a  <=> -z >= b/a, invert weights -> thr = ceil(b/a)
    a = 0: constant output     -> thr = -inf (always fire) or +inf (never)
    """
    zmax = np.abs(v).sum(1)
    thr = np.empty(len(a), dtype=np.int64)
    v = v.copy()
    for n in range(len(a)):
        if a[n] > 0:
            thr[n] = math.ceil(-b[n] / a[n])
        elif a[n] < 0:
            v[n] = -v[n]
            thr[n] = math.ceil(b[n] / a[n])
        else:
            thr[n] = -zmax[n] - 1 if b[n] >= 0 else zmax[n] + 1
        thr[n] = int(np.clip(thr[n], -zmax[n] - 1, zmax[n] + 1))
    return v, thr


@torch.no_grad()
def from_checkpoint(path: Path):
    ck = torch.load(path, map_location=DEVICE)
    cfg = ck["config"]
    if cfg["model"] not in ("bnn", "expanded"):
        raise SystemExit("golden model needs a bnn/expanded checkpoint")
    k = cfg.get("k", 1)
    model = BNN(cfg["n_in"], cfg["hidden"], k).to(DEVICE)
    model.load_state_dict(ck["state_dict"])
    model.eval()

    layers = []
    for fc, bn in zip(model.fcs, model.bns):
        v, u = fc.int_weight()
        s = torch.sqrt(bn.running_var + bn.eps)
        # BN(u*z) = gamma*(u*z - mu)/s + beta  ->  a*z + b
        a = (bn.weight * u / s).double().cpu().numpy()
        b = (bn.bias - bn.weight * bn.running_mean / s).double().cpu().numpy()
        layers.append((v.round().long().cpu().numpy(), fc.mask.cpu().numpy(), a, b))
    v, u = model.out.int_weight()
    a = np.array([(model.out_scale * u).item()], dtype=np.float64)
    b = np.array([model.out_bias.item()], dtype=np.float64)
    layers.append((v.round().long().cpu().numpy(), model.out.mask.cpu().numpy(), a, b))

    golden = []
    for v, mask, a, b in layers:
        v2, thr = _fold_threshold(v, a, b)
        g = GoldenLayer(decompose(v2, k, mask), mask.astype(bool), thr, k)
        assert np.array_equal(g.int_weights(), v2)
        golden.append(g)
    return golden, model, cfg


def golden_forward(layers: list[GoldenLayer], x01: np.ndarray, bs: int = 200_000) -> np.ndarray:
    out = np.empty(len(x01), dtype=np.uint8)
    for i in range(0, len(x01), bs):
        x = np.where(x01[i:i + bs] == 1, 1, -1)
        for g in layers:
            x = np.where(g.preact(x) >= g.thr[None, :], 1, -1)
        out[i:i + bs] = (x[:, 0] > 0).astype(np.uint8)
    return out


def hw_cost(layers: list[GoldenLayer]) -> dict:
    """Simple hardware cost proxies (independent of RTL micro-architecture)."""
    xnor_bits = sum(g.planes.shape[1] * (g.planes.shape[2] + (g.k - 1) * int(g.mask.sum())) for g in layers)
    return {
        "weight_bits": xnor_bits,           # stored weight bits actually used
        "xnor_ops_per_inference": xnor_bits,
        "threshold_words": sum(len(g.thr) for g in layers),
        "salient_channels": [int(g.mask.sum()) for g in layers],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("checkpoint", type=Path)
    ap.add_argument("--data", type=Path, help="default: dataset from the checkpoint config")
    args = ap.parse_args()

    layers, model, cfg = from_checkpoint(args.checkpoint)
    d = np.load(args.data or cfg["data"])
    x, y = d["test_x"], d["test_y"][:, 0]

    pred = golden_forward(layers, x)
    xt = torch.from_numpy(x.astype(np.float32)).to(DEVICE)
    with torch.no_grad():
        torch_pred = np.concatenate([(model(xt[i:i + 65536]) >= 0).cpu().numpy()
                                     for i in range(0, len(xt), 65536)]).astype(np.uint8)

    mism = int(np.sum(pred != torch_pred))
    print(f"{args.checkpoint.name}")
    print(f"  golden test LER   {np.mean(pred != y):.6f}")
    print(f"  pytorch test LER  {np.mean(torch_pred != y):.6f}")
    print(f"  golden vs pytorch mismatches: {mism} / {len(x)}")
    for key, val in hw_cost(layers).items():
        print(f"  {key}: {val}")
    for i, g in enumerate(layers):
        print(f"  layer {i}: {g.planes.shape[2]}->{g.planes.shape[1]}  k={g.k}  "
              f"thr range [{g.thr.min()}, {g.thr.max()}]")


if __name__ == "__main__":
    main()
