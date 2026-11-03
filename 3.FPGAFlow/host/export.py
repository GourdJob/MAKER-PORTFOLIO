"""Phase 3: export a trained BNN to the FPGA engine's plane format + golden vectors.

Engine format (one format for bnn / expanded / neuronexp):
  network = layers; layer = n_in, n_out, neurons; neuron = threshold + list of planes
  plane   = (w bits, mask bits, shift):  contributes  (2*popcount(XNOR(w, x) & mask) - popcount(mask)) << shift
  neuron fires (bit 1 = +1) iff  z = sum of plane contributions >= threshold
Input/activation bit i = 1 means +1 (detector fired), 0 means -1.

Outputs in <out>/ (default build/<checkpoint-stem>/):
  net.json          summary (sizes, plane counts, golden LER)
  layers.hex        per layer:  n_in(16) n_out(16) neuron_base(16) as 12 hex digits
  neurons.hex       per neuron: plane_start(16) n_planes(8) threshold(16, two's complement)
  planes.hex        per plane:  shift(8) mask(MAXW) w(MAXW), MSB first
  vectors.hex       first --n-vectors test shots: label(4) pred(4) input bits(MAXW)
  load.bin          UART command stream that loads this network (see rtl/README / hil.py)
  golden_test_pred.npy   golden prediction for every test shot (for HIL comparison)

  python host/export.py models/study/exp_d3_r3_p0.005_s5_k3_awq_L0n24.pt
"""

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import torch  # before numpy (duplicate OpenMP runtime on this machine otherwise)
import numpy as np

from golden import _fold_threshold, from_checkpoint
from train import DEVICE

MAXW = 256          # max inputs per layer / max neurons per layer in the engine
MAX_NEURONS = 1024  # neuron table depth
MAX_PLANES = 1024   # plane memory depth (1024 x 520 bits = 15 of the XC7S25's 45 BRAM36)

# UART protocol (host -> FPGA): 0xA5, type, payload..., checksum (8-bit sum of type+payload)
SOF = 0xA5
T_LAYER, T_NEURON, T_PLANE, T_NLAYERS, T_INFER = 0x01, 0x02, 0x03, 0x04, 0x10


@dataclass
class Neuron:
    thr: int
    planes: list = field(default_factory=list)  # (w: np.uint8[n_in], m: np.uint8[n_in], shift: int)


@dataclass
class Layer:
    n_in: int
    neurons: list


def _neurons_from_int(v: np.ndarray, thr: np.ndarray, planes_of) -> list:
    return [Neuron(int(thr[n]), planes_of(n)) for n in range(v.shape[0])]


def from_golden_layers(glayers) -> list[Layer]:
    """bnn / expanded checkpoints (golden.GoldenLayer: k planes, shared salient mask)."""
    layers = []
    for g in glayers:
        n_out, n_in = g.planes.shape[1:]
        full = np.ones(n_in, np.uint8)
        masks = [full] + [g.mask.astype(np.uint8)] * (g.k - 1)
        shifts = [g.k - 1 - i for i in range(g.k)]

        def planes_of(n, g=g, masks=masks, shifts=shifts):
            return [(g.planes[i][n].copy(), masks[i], shifts[i]) for i in range(g.k) if masks[i].any()]

        layers.append(Layer(n_in, _neurons_from_int(g.int_weights(), g.thr, planes_of)))
    return layers


@torch.no_grad()
def from_neuronexp(path: Path) -> tuple[list[Layer], torch.nn.Module, dict]:
    from neuronexp import NeuronExpBNN, parse_rank_units  # noqa: F401  (import for type)

    ck = torch.load(path, map_location=DEVICE)
    cfg = ck["config"]
    units = None if cfg["plain"] else _units_per_neuron(cfg, ck["chans"])
    model = NeuronExpBNN(cfg["n_in"], cfg["hidden"], ck["chans"], units).to(DEVICE)
    model.load_state_dict(ck["state_dict"])
    model.eval()

    def bn_affine(bn, u):
        s = torch.sqrt(bn.running_var + bn.eps)
        a = (bn.weight * u / s).double().cpu().numpy()
        b = (bn.bias - bn.weight * bn.running_mean / s).double().cpu().numpy()
        return a, b

    n_in = cfg["n_in"]
    full = np.ones(n_in, np.uint8)
    # layer 0 = main binary neurons + dedicated neurons
    v0, u0 = model.fc0.int_weight()
    v0 = v0.round().long().cpu().numpy()
    a0, b0 = bn_affine(model.bn0, u0)
    v0, t0 = _fold_threshold(v0, a0, b0)
    neurons = [Neuron(int(t0[n]), [((v0[n] > 0).astype(np.uint8), full, 0)]) for n in range(len(v0))]

    ded = model.ded
    vd = ded.int_weight().round().long().cpu().numpy()
    ad, bd = bn_affine(model.bnd, torch.tensor(1.0, device=DEVICE))
    vd_f, td = _fold_threshold(vd, ad, bd)
    term_sign = torch.where(ded.terms >= 0, 1, -1).cpu().numpy()
    scales = ded.scales.cpu().numpy()
    chans = ded.chan.cpu().numpy()
    for d in range(len(vd)):
        # _fold_threshold negates a row when its BN gain is negative; term bits must follow
        flip = -1 if not np.array_equal(vd_f[d], vd[d]) else 1
        j = chans[d]
        row = vd_f[d]
        if ded.plain:
            neurons.append(Neuron(int(td[d]), [((row > 0).astype(np.uint8), full, 0)]))
            continue
        m0 = full.copy()
        m0[j] = 0
        w0 = (row > 0).astype(np.uint8)
        planes = [(w0, m0, 0)]
        mj = np.zeros(n_in, np.uint8)
        mj[j] = 1
        for s, t in zip(scales[d], term_sign[d]):
            if s == 0:
                continue
            wbit = np.zeros(n_in, np.uint8)
            wbit[j] = 1 if flip * t > 0 else 0
            planes.append((wbit, mj, int(np.log2(s))))
        neurons.append(Neuron(int(td[d]), planes))
    layers = [Layer(n_in, neurons)]

    rest = list(zip(model.fcs, model.bns))
    for fc, bn in rest:
        v, u = fc.int_weight()
        a, b = bn_affine(bn, u)
        v, t = _fold_threshold(v.round().long().cpu().numpy(), a, b)
        layers.append(Layer(v.shape[1], [Neuron(int(t[n]), [((v[n] > 0).astype(np.uint8),
                                                             np.ones(v.shape[1], np.uint8), 0)])
                                         for n in range(len(v))]))
    v, u = model.out.int_weight()
    a = np.array([(model.out_scale * u).item()])
    b = np.array([model.out_bias.item()])
    v, t = _fold_threshold(v.round().long().cpu().numpy(), a, b)
    layers.append(Layer(v.shape[1], [Neuron(int(t[0]), [((v[0] > 0).astype(np.uint8),
                                                         np.ones(v.shape[1], np.uint8), 0)])]))
    return layers, model, cfg


def _units_per_neuron(cfg, chans):
    from neuronexp import TIERED, parse_rank_units

    spec = cfg["units"]
    spec = TIERED if spec == "tiered" else spec
    per_rank = parse_rank_units(spec)
    units, prev, r = [], None, -1
    for j in chans:  # chans lists each salient detector's neurons contiguously, in rank order
        if j != prev:
            r, prev, i = r + 1, j, 0
        rank_units = per_rank[min(r, len(per_rank) - 1)]
        units.append(rank_units[i])
        i += 1
    return units


def dense_weights(layer: Layer) -> np.ndarray:
    """Reconstruct the integer weight matrix from the planes (what the engine computes)."""
    v = np.zeros((len(layer.neurons), layer.n_in), np.int64)
    for n, neu in enumerate(layer.neurons):
        for w, m, s in neu.planes:
            v[n] += (2 * w.astype(np.int64) - 1) * m * (1 << s)
    return v


def engine_forward(layers: list[Layer], x01: np.ndarray, bs: int = 200_000) -> np.ndarray:
    mats = [(torch.from_numpy(dense_weights(l).astype(np.float64)).to(DEVICE),
             torch.tensor([n.thr for n in l.neurons], device=DEVICE, dtype=torch.float64)) for l in layers]
    out = np.empty(len(x01), np.uint8)
    for i in range(0, len(x01), bs):
        x = torch.from_numpy(np.where(x01[i:i + bs] == 1, 1.0, -1.0)).to(DEVICE)
        for v, thr in mats:
            x = torch.where(torch.round(x @ v.T) >= thr, 1.0, -1.0).double()
        out[i:i + bs] = (x[:, 0] > 0).cpu().numpy().astype(np.uint8)
    return out


def check_limits(layers: list[Layer]):
    n_neu = sum(len(l.neurons) for l in layers)
    n_pl = sum(len(n.planes) for l in layers for n in l.neurons)
    for i, l in enumerate(layers):
        assert l.n_in <= MAXW and len(l.neurons) <= MAXW, f"layer {i} exceeds MAXW={MAXW}"
        if i:
            assert l.n_in == len(layers[i - 1].neurons), f"layer {i} n_in mismatch"
        for n in l.neurons:
            assert -32768 <= n.thr <= 32767 and 0 <= len(n.planes) <= 255
            assert all(0 <= s <= 7 for _, _, s in n.planes)
    assert n_neu <= MAX_NEURONS and n_pl <= MAX_PLANES, (n_neu, n_pl)
    return n_neu, n_pl


def bits_to_int(bits: np.ndarray) -> int:
    """bit i of the result = bits[i]."""
    return int("".join("1" if b else "0" for b in bits[::-1]) or "0", 2)


def frame(t: int, payload: bytes) -> bytes:
    return bytes([SOF, t]) + payload + bytes([(t + sum(payload)) & 0xFF])


def u16(v: int) -> bytes:
    return (v & 0xFFFF).to_bytes(2, "little")


def infer_frame(seq: int, x01: np.ndarray, label: int) -> bytes:
    x = bits_to_int(x01.astype(np.uint8)).to_bytes(MAXW // 8, "little")
    return frame(T_INFER, bytes([seq & 0xFF, label & 1]) + x)


def write_outputs(layers: list[Layer], out: Path, x: np.ndarray, y: np.ndarray, pred: np.ndarray,
                  n_vec: int, info: dict):
    out.mkdir(parents=True, exist_ok=True)
    n_neu, n_pl = check_limits(layers)
    hexw = MAXW // 4
    lay_lines, neu_lines, pl_lines, stream = [], [], [], bytearray()
    nb, pb = 0, 0
    for li, l in enumerate(layers):
        lay_lines.append(f"{l.n_in:04x}{len(l.neurons):04x}{nb:04x}")
        stream += frame(T_LAYER, bytes([li]) + u16(l.n_in) + u16(len(l.neurons)) + u16(nb))
        for neu in l.neurons:
            neu_lines.append(f"{pb:04x}{len(neu.planes):02x}{neu.thr & 0xFFFF:04x}")
            stream += frame(T_NEURON, u16(nb) + u16(pb) + bytes([len(neu.planes)]) + u16(neu.thr))
            for w, m, s in neu.planes:
                wi, mi = bits_to_int(w), bits_to_int(m)
                pl_lines.append(f"{s:02x}{mi:0{hexw}x}{wi:0{hexw}x}")
                stream += frame(T_PLANE, u16(pb) + bytes([s]) + mi.to_bytes(MAXW // 8, "little")
                                + wi.to_bytes(MAXW // 8, "little"))
                pb += 1
            nb += 1
    stream += frame(T_NLAYERS, bytes([len(layers)]))
    (out / "layers.hex").write_text("\n".join(lay_lines) + "\n")
    (out / "neurons.hex").write_text("\n".join(neu_lines) + "\n")
    (out / "planes.hex").write_text("\n".join(pl_lines) + "\n")
    (out / "load.bin").write_bytes(bytes(stream))
    vec = [f"{int(y[i]):01x}{int(pred[i]):01x}{bits_to_int(x[i]):0{hexw}x}" for i in range(min(n_vec, len(x)))]
    (out / "vectors.hex").write_text("\n".join(vec) + "\n")
    np.save(out / "golden_test_pred.npy", pred)
    info.update(n_layers=len(layers), n_neurons=n_neu, n_planes=n_pl,
                layer_sizes=[(l.n_in, len(l.neurons)) for l in layers], load_bytes=len(stream),
                n_vectors=min(n_vec, len(x)), maxw=MAXW)
    (out / "net.json").write_text(json.dumps(info, indent=2))
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("checkpoint", type=Path)
    ap.add_argument("--data", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--n-vectors", type=int, default=2000)
    args = ap.parse_args()

    cfg = torch.load(args.checkpoint, map_location="cpu")["config"]
    if cfg["model"] == "neuronexp":
        layers, model, cfg = from_neuronexp(args.checkpoint)
    else:
        glayers, model, cfg = from_checkpoint(args.checkpoint)
        layers = from_golden_layers(glayers)

    d = np.load(args.data or cfg["data"])
    x, y = d["test_x"], d["test_y"][:, 0]
    pred = engine_forward(layers, x)
    xt = torch.from_numpy(x.astype(np.float32)).to(DEVICE)
    with torch.no_grad():
        tp = np.concatenate([(model(xt[i:i + 65536]) >= 0).cpu().numpy()
                             for i in range(0, len(xt), 65536)]).astype(np.uint8)
    info = {"checkpoint": str(args.checkpoint), "data": str(args.data or cfg["data"]),
            "golden_test_ler": float(np.mean(pred != y)), "pytorch_test_ler": float(np.mean(tp != y)),
            "golden_vs_pytorch_mismatches": int(np.sum(pred != tp)), "test_shots": int(len(x))}
    out = args.out or Path("build") / args.checkpoint.stem
    info = write_outputs(layers, out, x, y, pred, args.n_vectors, info)
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
