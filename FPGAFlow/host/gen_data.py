"""Phase 1: generate surface-code syndrome datasets with Stim + PyMatching baseline.

For each physical error rate p this writes:
  data/d{d}_r{rounds}_p{p}.npz   train/calib/test detector bits + observable flips
  data/d{d}_r{rounds}_p{p}.stim  the exact circuit used (for reproducibility)
and a summary data/baseline_d{d}_r{rounds}.json with PyMatching / trivial LER.

Example:
  python host/gen_data.py --d 3 --p 0.001 0.003 0.005 0.01
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pymatching
import stim


def make_circuit(d: int, rounds: int, p: float) -> stim.Circuit:
    """Rotated surface-code Z-memory with uniform circuit-level depolarizing noise."""
    return stim.Circuit.generated(
        "surface_code:rotated_memory_z",
        distance=d,
        rounds=rounds,
        after_clifford_depolarization=p,
        before_round_data_depolarization=p,
        before_measure_flip_probability=p,
        after_reset_flip_probability=p,
    )


def sample(circuit: stim.Circuit, shots: int, seed: int):
    sampler = circuit.compile_detector_sampler(seed=seed)
    dets, obs = sampler.sample(shots, separate_observables=True)
    return dets.astype(np.uint8), obs.astype(np.uint8)


def logical_error_rate(pred: np.ndarray, truth: np.ndarray) -> float:
    """Fraction of shots where any observable prediction is wrong."""
    return float(np.mean(np.any(pred != truth, axis=1)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--d", type=int, default=3, help="code distance")
    ap.add_argument("--rounds", type=int, default=None, help="syndrome rounds (default: d)")
    ap.add_argument("--p", type=float, nargs="+", default=[0.001, 0.003, 0.005, 0.01])
    ap.add_argument("--train", type=int, default=1_000_000, help="training shots per p")
    ap.add_argument("--calib", type=int, default=10_000, help="calibration shots per p (saliency)")
    ap.add_argument("--test", type=int, default=1_000_000, help="test shots per p")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--out", type=Path, default=Path("data"))
    args = ap.parse_args()

    rounds = args.rounds or args.d
    args.out.mkdir(parents=True, exist_ok=True)
    summary = {"d": args.d, "rounds": rounds, "noise": "uniform circuit-level depolarizing",
               "seed": args.seed, "results": []}

    print(f"d={args.d} rounds={rounds}  shots: train={args.train} calib={args.calib} test={args.test}")
    print(f"{'p':>8} {'dets':>5} {'obs':>4} {'flip rate':>10} {'trivial LER':>12} {'PyMatching LER':>15} {'errors':>7}")

    for i, p in enumerate(args.p):
        t0 = time.time()
        circuit = make_circuit(args.d, rounds, p)
        # Distinct, deterministic seeds per (p, split) so splits never overlap.
        base = args.seed + 1000 * i
        train_x, train_y = sample(circuit, args.train, base + 1)
        calib_x, calib_y = sample(circuit, args.calib, base + 2)
        test_x, test_y = sample(circuit, args.test, base + 3)

        dem = circuit.detector_error_model(decompose_errors=True)
        matching = pymatching.Matching.from_detector_error_model(dem)
        mwpm_pred = matching.decode_batch(test_x).astype(np.uint8)
        mwpm_ler = logical_error_rate(mwpm_pred, test_y)
        trivial_ler = logical_error_rate(np.zeros_like(test_y), test_y)
        n_err = int(np.sum(np.any(mwpm_pred != test_y, axis=1)))

        stem = f"d{args.d}_r{rounds}_p{p:g}"
        np.savez_compressed(
            args.out / f"{stem}.npz",
            train_x=train_x, train_y=train_y,
            calib_x=calib_x, calib_y=calib_y,
            test_x=test_x, test_y=test_y,
            mwpm_test_pred=mwpm_pred,
            d=args.d, rounds=rounds, p=p,
        )
        (args.out / f"{stem}.stim").write_text(str(circuit))

        summary["results"].append({
            "p": p, "file": f"{stem}.npz",
            "num_detectors": circuit.num_detectors,
            "num_observables": circuit.num_observables,
            "test_shots": args.test,
            "observable_flip_rate": float(test_y.mean()),
            "trivial_ler": trivial_ler,
            "pymatching_ler": mwpm_ler,
            "pymatching_errors": n_err,
        })
        print(f"{p:>8g} {circuit.num_detectors:>5} {circuit.num_observables:>4} "
              f"{test_y.mean():>10.5f} {trivial_ler:>12.5f} {mwpm_ler:>15.6f} {n_err:>7}"
              f"   ({time.time() - t0:.1f}s)")

    out_json = args.out / f"baseline_d{args.d}_r{rounds}.json"
    out_json.write_text(json.dumps(summary, indent=2))
    print(f"wrote {out_json}")


if __name__ == "__main__":
    main()
