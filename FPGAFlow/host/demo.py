"""Live demo for screen recording: the FPGA decodes quantum-error syndromes in real time.

Loads the network onto the board, streams test shots, and shows a live readout of the
FPGA's logical error rate vs PyMatching, plus the bit-exact check against the golden model.

  python host/demo.py                         (defaults: COM10, the best exported model, 50,000 shots)
  python host/demo.py --port COM10 --n 200000
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
sys.stdout.reconfigure(encoding="utf-8")  # block characters; Windows consoles default to cp1252
B, DIM, BLUE, GREEN, RED, RST = "\033[1m", "\033[2m", "\033[94m", "\033[92m", "\033[91m", "\033[0m"
UP, CLR = "\033[F", "\033[K"


def bar(frac: float, width: int = 40) -> str:
    n = int(frac * width)
    return f"{BLUE}{'█' * n}{DIM}{'░' * (width - n)}{RST}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="COM10")
    ap.add_argument("--model", type=Path, default=Path("build/exp_d3_r3_p0.005_s5_k3_awq_L0n24"))
    ap.add_argument("--n", type=int, default=50_000)
    ap.add_argument("--offset", type=int, default=0, help="start at this test-shot index")
    ap.add_argument("--chunk", type=int, default=250)
    args = ap.parse_args()

    info = json.loads((args.model / "net.json").read_text())
    d = np.load(info["data"])
    s = slice(args.offset, args.offset + args.n)
    x, y, mwpm = d["test_x"][s], d["test_y"][s, 0], d["mwpm_test_pred"][s, 0]
    golden = np.load(args.model / "golden_test_pred.npy")[s]
    n = len(x)

    print(f"\n{B}  Quantum error-correction decoder on an FPGA{RST}")
    print(f"{DIM}  distance-3 surface code · physical error rate 0.5% · binary neural network on a Spartan-7{RST}\n")

    ser = serial.Serial(args.port, BAUD, timeout=0.05)
    ser.reset_input_buffer()
    ser.write(bytes(80))
    time.sleep(0.05)
    ser.reset_input_buffer()

    frames = split_frames((args.model / "load.bin").read_bytes())
    t0 = time.time()
    ser.write(b"".join(frames))
    acks = read_replies(ser, len(frames))
    ok = len(acks) == len(frames) and all(a[0] not in (-1, 0xEE) for a in acks)
    print(f"  Loading network onto the FPGA: {info['n_neurons']} neurons, {info['n_planes']} weight planes "
          f"... {GREEN + 'done' if ok else RED + 'FAILED'}{RST} ({time.time() - t0:.1f} s)\n")
    if not ok:
        sys.exit(1)

    lines = 6
    print("\n" * (lines - 1))
    pred = np.zeros(n, np.uint8)
    t0 = time.time()
    for start in range(0, n, args.chunk):
        idx = range(start, min(start + args.chunk, n))
        ser.write(b"".join(infer_frame(i & 0xFF, x[i], int(y[i])) for i in idx))
        reps = read_replies(ser, len(idx))
        if len(reps) != len(idx):
            sys.exit(f"\n{RED}  board stopped replying{RST}")
        for i, (t, seq, res) in zip(idx, reps):
            pred[i] = res & 1 if t == T_INFER and seq == (i & 0xFF) else 255
        k = idx[-1] + 1
        fpga = np.mean(pred[:k] != y[:k])
        pm = np.mean(mwpm[:k] != y[:k])
        mism = int(np.sum(pred[:k] != golden[:k]))
        rate = k / (time.time() - t0)
        out = [
            f"  {bar(k / n)}  {k:>9,} / {n:,} syndromes   {rate:,.0f} per second",
            "",
            f"  {B}FPGA decoder{RST}       logical error rate  {B}{BLUE}{fpga * 100:6.3f}%{RST}"
            f"   ({int(np.sum(pred[:k] != y[:k])):,} errors)",
            f"  PyMatching         logical error rate  {pm * 100:6.3f}%   ({int(np.sum(mwpm[:k] != y[:k])):,} errors)",
            "",
            f"  Bit-exact check vs golden model:  "
            + (f"{GREEN}{B}{mism} mismatches{RST}" if mism == 0 else f"{RED}{B}{mism} mismatches{RST}"),
        ]
        sys.stdout.write((UP + CLR) * lines + "\n".join(out) + "\n")
        sys.stdout.flush()

    print(f"\n  {B}Done.{RST} {n:,} syndromes decoded on the FPGA in {time.time() - t0:.1f} s.\n")


if __name__ == "__main__":
    main()
