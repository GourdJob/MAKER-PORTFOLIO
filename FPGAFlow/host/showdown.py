"""Live FPGA showdown for video: loads each decoder design onto the board in turn, decodes the
same test shots with each, and ends with a scoreboard against PyMatching.

  python host/showdown.py                      (defaults: COM10, 100,000 shots per design)
  python host/showdown.py --n 30000 --pause    (wait for Enter before each design, for narration)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import serial

from export import T_INFER, infer_frame
from hil import BAUD, read_replies, split_frames

os.system("")  # enable ANSI escape codes in the Windows console
sys.stdout.reconfigure(encoding="utf-8")
B, DIM, BLUE, GREEN, RED, YEL, RST = "\033[1m", "\033[2m", "\033[94m", "\033[92m", "\033[91m", "\033[93m", "\033[0m"
UP, CLR = "\033[F", "\033[K"

# (build folder, short name, one-line description) in story order
DESIGNS = [
    ("bnn_d3_r3_p0.005_w128_seed2", "Plain binary network",
     "every weight is +1 or -1 (the starting point)"),
    ("nexp_d3_r3_p0.005_n12_awq_uniform_seed3", "My design: neuron expansion",
     "12 salient detectors get 60 extra neurons with +-2 / +-4 / +-7 weights"),
    ("exp_d3_r3_p0.005_s5_k3_awq_L0n12_seed4", "Standard: 3-bit weights, 12 detectors",
     "the same 12 detectors get 3-bit weights inside the existing neurons"),
    ("exp_d3_r3_p0.005_s5_k3_awq_L0n24", "Standard: 3-bit weights, all 24 detectors",
     "the whole first layer gets 3-bit weights"),
]


def bar(frac: float, width: int = 36, color: str = BLUE) -> str:
    n = max(0, min(width, int(round(frac * width))))
    return f"{color}{'█' * n}{DIM}{'░' * (width - n)}{RST}"


def open_port(port: str) -> serial.Serial:
    ser = serial.Serial(port, BAUD, timeout=0.05)
    ser.reset_input_buffer()
    ser.write(bytes(80))  # flush any half-received frame on the FPGA
    time.sleep(0.05)
    ser.reset_input_buffer()
    return ser


def run_design(ser, folder: Path, title: str, desc: str, x, y, mwpm, chunk: int):
    info = json.loads((folder / "net.json").read_text())
    golden = np.load(folder / "golden_test_pred.npy")[:len(x)]
    n = len(x)
    print(f"  {B}{title}{RST}")
    print(f"  {DIM}{desc}{RST}")

    frames = split_frames((folder / "load.bin").read_bytes())
    t0 = time.time()
    ser.write(b"".join(frames))
    acks = read_replies(ser, len(frames))
    ok = len(acks) == len(frames) and all(a[0] not in (-1, 0xEE) for a in acks)
    print(f"  loading onto FPGA: {info['n_neurons']} neurons, {info['n_planes']} weight planes ... "
          f"{GREEN + 'done' if ok else RED + 'FAILED'}{RST} ({time.time() - t0:.1f} s)")
    if not ok:
        sys.exit(1)

    pred = np.zeros(n, np.uint8)
    print("\n")
    t0 = time.time()
    for start in range(0, n, chunk):
        idx = range(start, min(start + chunk, n))
        ser.write(b"".join(infer_frame(i & 0xFF, x[i], int(y[i])) for i in idx))
        reps = read_replies(ser, len(idx))
        if len(reps) != len(idx):
            sys.exit(f"\n{RED}  board stopped replying{RST}")
        for i, (t, seq, res) in zip(idx, reps):
            pred[i] = res & 1 if t == T_INFER and seq == (i & 0xFF) else 255
        k = idx[-1] + 1
        ler = np.mean(pred[:k] != y[:k])
        mism = int(np.sum(pred[:k] != golden[:k]))
        rate = k / (time.time() - t0)
        exact = f"{GREEN}bit-exact{RST}" if mism == 0 else f"{RED}{mism} mismatches{RST}"
        sys.stdout.write((UP + CLR) * 2
                         + f"  {bar(k / n)} {k:>8,} / {n:,} shots  {rate:,.0f}/s\n"
                         + f"  logical error rate {B}{BLUE}{ler * 100:5.2f}%{RST}   "
                           f"({int(np.sum(pred[:k] != y[:k])):,} errors)   {exact}\n")
        sys.stdout.flush()
    print()
    return {"title": title, "ler": float(np.mean(pred != y)), "mism": int(np.sum(pred != golden)),
            "planes": info["n_planes"], "neurons": info["n_neurons"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="COM10")
    ap.add_argument("--n", type=int, default=100_000, help="test shots per design (same shots for every design)")
    ap.add_argument("--chunk", type=int, default=500)
    ap.add_argument("--pause", action="store_true", help="wait for Enter before each design")
    args = ap.parse_args()

    info = json.loads((Path("build") / DESIGNS[0][0] / "net.json").read_text())
    d = np.load(info["data"])
    x, y, mwpm = d["test_x"][:args.n], d["test_y"][:args.n, 0], d["mwpm_test_pred"][:args.n, 0]
    pm = float(np.mean(mwpm != y))

    print(f"\n{B}  FPGA showdown: which decoder design wins?{RST}")
    print(f"{DIM}  distance-3 surface code · 0.5% physical error rate · Spartan-7 XC7S25 · "
          f"the same {args.n:,} syndromes for every design{RST}\n")
    ser = open_port(args.port)
    results = []
    for i, (folder, title, desc) in enumerate(DESIGNS, 1):
        if args.pause:
            input(f"  {DIM}[Enter] to run design {i} of {len(DESIGNS)}{RST}")
            sys.stdout.write(UP + CLR)
        results.append(run_design(ser, Path("build") / folder, f"{i}. {title}", desc, x, y, mwpm, args.chunk))

    if args.pause:
        input(f"  {DIM}[Enter] for the scoreboard{RST}")
        sys.stdout.write(UP + CLR)
    rows = [(r["title"][3:], r["ler"], r) for r in results] + [("PyMatching (standard software decoder)", pm, None)]
    top = max(v for _, v, _ in rows)
    print(f"  {B}Scoreboard{RST}  {DIM}(logical error rate, lower is better){RST}\n")
    for name, v, r in sorted(rows, key=lambda t: t[1]):
        color = YEL if r is None else (GREEN if v < pm else BLUE)
        tag = "" if r is None else (f"{GREEN}beats PyMatching{RST}" if v < pm else "")
        print(f"  {name:<44} {bar(v / top, 30, color)} {B}{v * 100:5.2f}%{RST}  {tag}")
    mism = sum(r["mism"] for r in results)
    print(f"\n  Hardware vs software model: "
          + (f"{GREEN}{B}0 mismatches{RST} across all {len(results) * args.n:,} decodes"
             if mism == 0 else f"{RED}{B}{mism} mismatches{RST}") + "\n")


if __name__ == "__main__":
    main()
