"""Send messages to the RS(8,4) demo on the Cmod S7 and show what happened to each one.

Usage:  pip install pyserial
        python rs_host.py COM5 [count]             send `count` random 16-bit messages (default 10)
        python rs_host.py COM5 --hex 1234 BEEF     send these exact messages (4 hex digits = 4 symbols)
        python rs_host.py COM5 --text "Hi there"   send a string, 2 characters per message
        add --delay SECONDS to pause after each message (the display shows the corrupted word for 2 s,
        then the corrected word - use --delay 4 or more to watch both)

Each message is 4 data symbols (hex digits). The FPGA encodes them into 8 symbols, corrupts 0..3 of them
(press BTN0 to change how many), decodes, and replies with 10 bytes:
  corrupted codeword (4), decoded message (2), status 'O'/'C'/'X', symbols fixed '0'..'2',
  injected-position mask, fixed-position mask.
"""
import random
import sys
import time

import serial

port = sys.argv[1]
args = sys.argv[2:]
delay = 0.0
if "--delay" in args:
    i = args.index("--delay")
    delay = float(args[i + 1])
    del args[i:i + 2]

text_mode = bool(args) and args[0] == "--text"
if args and args[0] == "--hex":
    msgs = [int(h, 16) & 0xFFFF for h in args[1:]]
elif text_mode:
    data = " ".join(args[1:]).encode("latin-1")
    if len(data) % 2:
        data += b" "
    msgs = [(data[i] << 8) | data[i + 1] for i in range(0, len(data), 2)]
else:
    count = int(args[0]) if args else 10
    msgs = [random.randrange(1 << 16) for _ in range(count)]


def symbols(word, nsym, mask=0):
    """Hex digits, most significant first; a '.' after each digit whose bit is set in mask."""
    out = []
    for i in range(nsym - 1, -1, -1):
        out.append(f"{(word >> (4 * i)) & 15:X}" + ("." if mask >> i & 1 else " "))
    return "".join(out)


stats = {"O": 0, "C": 0, "X": 0, "MISCORRECTED": 0}
received = bytearray()

with serial.Serial(port, 115200, timeout=1) as ser:
    ser.reset_input_buffer()
    for m in msgs:
        ser.write(bytes([m >> 8, m & 0xFF]))
        r = ser.read(10)
        if len(r) != 10:
            print(f"sent {m:04X}: got {len(r)} of 10 reply bytes (check port/bitstream, press BTN1)")
            continue
        rx_word = int.from_bytes(r[0:4], "big")
        decoded = (r[4] << 8) | r[5]
        received += r[4:6]
        status, nfixed, inj, fixed = chr(r[6]), chr(r[7]), r[8], r[9]
        verdict = status
        if status == "C" and decoded != m:
            verdict = "MISCORRECTED"
        elif status != "X" and decoded != m:
            verdict = "WRONG"
        stats[verdict] = stats.get(verdict, 0) + 1
        fixed_at = ",".join(f"c{i}" for i in range(7, -1, -1) if fixed >> i & 1) or "-"
        note = "" if verdict == status else "  <-- " + verdict
        print(f"sent {m:04X}  corrupted {symbols(rx_word, 8, inj)} decoded {decoded:04X}  "
              f"status {status}  fixed {nfixed} ({fixed_at}){note}")
        time.sleep(delay)

print({k: v for k, v in stats.items() if v})
if text_mode:
    print(f"sent text:    {data.decode('latin-1')!r}")
    print(f"decoded text: {received.decode('latin-1', errors='replace')!r}")
if stats.get("WRONG"):
    print("some data came back wrong without an 'X' flag and with no correction - that should never happen")
