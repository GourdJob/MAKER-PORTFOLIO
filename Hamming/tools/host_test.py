"""Send bytes to the Cmod S7 over USB-UART and check the reply.

Usage:  pip install pyserial
        python host_test.py COM5 [count]            send `count` random bytes, one at a time (default 20)
        python host_test.py COM5 --hex 55 A7 FF     send these exact byte values (hex), one at a time
        python host_test.py COM5 --text "Hello"     send the characters of a string, one at a time
        python host_test.py COM5 --burst N          write N random bytes at once (N <= 16, the RX FIFO depth)
        add --delay SECONDS to any one-at-a-time mode to pause after each byte (for watching the LEDs)

Reply per byte: recovered byte, then a status char ('O' ok, 'C' corrected, 'X' double error).
Press BTN0 on the board to cycle the injected error count (0 -> 1 -> 2 -> 0).
"""
import random
import sys
import time

import serial

port = sys.argv[1]
args = sys.argv[2:]
burst = 0
to_send = None
delay = 0.0
if "--delay" in args:                 # seconds to wait after each byte, so the LEDs can be watched
    i = args.index("--delay")
    delay = float(args[i + 1])
    del args[i:i + 2]

if args and args[0] == "--burst":
    burst = int(args[1])
elif args and args[0] == "--hex":
    to_send = [int(h, 16) for h in args[1:]]
elif args and args[0] == "--text":
    to_send = list(" ".join(args[1:]).encode("latin-1"))
else:
    count = int(args[0]) if args else 20
    to_send = [random.randrange(256) for _ in range(count)]

stats = {"O": 0, "C": 0, "X": 0}
bad_data = 0


def show(b):
    return chr(b) if 32 <= b < 127 else "."


def check(sent, got, status):
    global bad_data
    stats[status] = stats.get(status, 0) + 1
    ok = got == sent
    if status != "X" and not ok:
        bad_data += 1
    print(f"sent {sent:02X} '{show(sent)}' {sent:08b}  got {got:02X} '{show(got)}' {got:08b}  "
          f"status {status} {'match' if ok else 'MISMATCH'}")


with serial.Serial(port, 115200, timeout=1) as ser:
    ser.reset_input_buffer()
    if burst:
        sent = [random.randrange(256) for _ in range(burst)]
        ser.write(bytes(sent))
        reply = ser.read(2 * burst)
        if len(reply) != 2 * burst:
            print(f"burst of {burst}: got {len(reply)} of {2 * burst} reply bytes (bytes were dropped)")
        for i in range(len(reply) // 2):
            check(sent[i], reply[2 * i], chr(reply[2 * i + 1]))
    else:
        for sent in to_send:
            ser.write(bytes([sent]))
            reply = ser.read(2)
            if len(reply) != 2:
                print(f"sent {sent:02X}: no reply (check pins/baud)")
                continue
            check(sent, reply[0], chr(reply[1]))
            time.sleep(delay)

print(stats)
if bad_data:
    print(f"{bad_data} byte(s) came back wrong without an 'X' flag - that should never happen")
