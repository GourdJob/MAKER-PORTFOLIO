"""Phase 5: hardware-in-the-loop test on the PLTW S7.

Loads an exported network (build/<model>/load.bin) over UART, streams test shots as INFER
frames, and checks every FPGA prediction bit-for-bit against the golden model.

  python host/hil.py --port COM10 --model build/exp_d3_r3_p0.005_s5_k3_awq_L0n24 --n 100000
  python host/hil.py --port COM10 --model build/... --n all          # full 1M test set (~7 min)
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import serial

from export import MAXW, T_INFER, infer_frame

BAUD = 1_000_000
PAYLOAD_LEN = {0x01: 7, 0x02: 7, 0x03: 3 + 2 * (MAXW // 8), 0x04: 1, 0x10: 2 + MAXW // 8}
ERR_CODES = {1: "bad checksum", 2: "unknown type", 3: "engine busy"}


def split_frames(stream: bytes) -> list[bytes]:
    frames, i = [], 0
    while i < len(stream):
        assert stream[i] == 0xA5, f"bad SOF at byte {i}"
        n = 3 + PAYLOAD_LEN[stream[i + 1]]
        frames.append(stream[i:i + n])
        i += n
    return frames


def read_replies(ser: serial.Serial, n: int, timeout: float = 5.0) -> list[tuple[int, int, int]]:
    """Read n 5-byte replies (0x5A, type, b1, b2, chk). Resyncs on 0x5A."""
    out, buf, t_end = [], bytearray(), time.time() + timeout
    while len(out) < n and time.time() < t_end:
        buf += ser.read(max(1, min(ser.in_waiting, 5 * (n - len(out)))))
        while len(buf) >= 5:
            if buf[0] != 0x5A:
                del buf[0]
                continue
            t, b1, b2, chk = buf[1], buf[2], buf[3], buf[4]
            del buf[:5]
            if (t + b1 + b2) & 0xFF != chk:
                out.append((-1, b1, b2))  # corrupted reply
            else:
                out.append((t, b1, b2))
            t_end = time.time() + timeout
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="COM10")
    ap.add_argument("--model", type=Path, required=True, help="export directory (build/<name>)")
    ap.add_argument("--n", default="100000", help="test shots to run, or 'all'")
    ap.add_argument("--chunk", type=int, default=500, help="frames per write")
    args = ap.parse_args()

    info = json.loads((args.model / "net.json").read_text())
    d = np.load(info["data"])
    x, y = d["test_x"], d["test_y"][:, 0]
    mwpm = d["mwpm_test_pred"][:, 0]
    golden = np.load(args.model / "golden_test_pred.npy")
    n = len(x) if args.n == "all" else min(int(args.n), len(x))

    ser = serial.Serial(args.port, BAUD, timeout=0.05)
    ser.reset_input_buffer()
    # flush any half-received frame in the FPGA parser (zeros fill it, checksum fails, parser resyncs)
    ser.write(bytes(80))
    time.sleep(0.05)
    ser.reset_input_buffer()

    # ---------------- load the network
    frames = split_frames((args.model / "load.bin").read_bytes())
    t0 = time.time()
    ser.write(b"".join(frames))
    acks = read_replies(ser, len(frames))
    bad = [a for a in acks if a[0] in (-1, 0xEE)]
    print(f"load: {len(frames)} commands, {len(acks)} replies, {len(bad)} errors ({time.time() - t0:.2f}s)")
    if len(acks) != len(frames) or bad:
        for a in bad[:5]:
            print("  error reply:", a, ERR_CODES.get(a[1], ""))
        sys.exit("network load failed: check the board is programmed, the port, and the baud rate")

    # ---------------- stream inferences
    pred = np.full(n, 255, np.uint8)
    errors, t0 = 0, time.time()
    for start in range(0, n, args.chunk):
        idx = range(start, min(start + args.chunk, n))
        ser.write(b"".join(infer_frame(i & 0xFF, x[i], int(y[i])) for i in idx))
        reps = read_replies(ser, len(idx))
        if len(reps) != len(idx):
            sys.exit(f"timeout: {len(reps)}/{len(idx)} replies for frames {start}..")
        for i, (t, seq, res) in zip(idx, reps):
            if t != T_INFER or seq != (i & 0xFF):
                errors += 1
                continue
            pred[i] = res & 1
            assert (res >> 1) & 1 == y[i], "label echo mismatch"
        done = idx[-1] + 1
        if done % (args.chunk * 20) == 0 or done == n:
            rate = done / (time.time() - t0)
            mm = int(np.sum(pred[:done] != golden[:done]))
            print(f"  {done:>8}/{n}  {rate:6.0f} shots/s  mismatches vs golden: {mm}  bad replies: {errors}",
                  flush=True)

    mism = int(np.sum(pred != golden[:n]))
    res = {
        "model": str(args.model), "shots": n, "mismatches_vs_golden": mism, "bad_replies": errors,
        "fpga_ler": float(np.mean(pred != y[:n])), "golden_ler": float(np.mean(golden[:n] != y[:n])),
        "pymatching_ler": float(np.mean(mwpm[:n] != y[:n])), "shots_per_s": round(n / (time.time() - t0)),
    }
    print(json.dumps(res, indent=2))
    out = args.model / "hil_result.json"
    out.write_text(json.dumps(res, indent=2))
    print("PASS (bit-exact)" if mism == 0 and errors == 0 else "FAIL")


if __name__ == "__main__":
    main()
