"""Bit-exact Python reference model of the RS(8,4) codec in src/.

    python rs_ref.py            self-test, print constants, write sim/vectors.mem

Code: GF(16) with primitive polynomial x^4 + x + 1 (alpha = 2), shortened RS(15,11) -> RS(8,4),
generator roots alpha^1..alpha^4 (fcr = 1), corrects up to t = 2 symbol errors.
Codeword word[31:0] = {c7, c6, ..., c0}; c7..c4 = data m3..m0, c3..c0 = parity.

The decoder mirrors rs_bm.v / rs_chien_forney.v step for step (same Berlekamp-Massey form,
same failure rules), so 3-error results can be compared exactly against the RTL.
"""
import itertools
import os
import random

PRIM = 0b10011  # x^4 + x + 1

# ---------------------------------------------------------------- GF(16)
EXP = [0] * 30
LOG = [0] * 16
v = 1
for i in range(15):
    EXP[i] = v
    LOG[v] = i
    v <<= 1
    if v & 0x10:
        v ^= PRIM
for i in range(15, 30):
    EXP[i] = EXP[i - 15]


def mul(a, b):
    if a == 0 or b == 0:
        return 0
    return EXP[LOG[a] + LOG[b]]


def inv(a):
    assert a != 0
    return EXP[(15 - LOG[a]) % 15]


def alpha(k):
    return EXP[k % 15]


def poly_eval(p, x):
    """p[i] is the coefficient of x^i."""
    y = 0
    for c in reversed(p):
        y = mul(y, x) ^ c
    return y


# ---------------------------------------------------------------- encoder
def generator():
    g = [1]
    for j in range(1, 5):
        root = alpha(j)
        nxt = [0] * (len(g) + 1)
        for i, c in enumerate(g):
            nxt[i + 1] ^= c           # x * g
            nxt[i] ^= mul(c, root)    # root * g  (minus == plus in GF(2^m))
        g = nxt
    return g  # g[0..4], g[4] = 1


G = generator()


def encode(msg):
    """msg = [m3, m2, m1, m0] -> codeword list c[0..7] (index = power of x)."""
    p = [0, 0, 0, 0]  # p[3]..p[0] are the LFSR stages, same order as rs_encoder.v
    for d in msg:
        fb = d ^ p[3]
        p = [mul(fb, G[0]), p[0] ^ mul(fb, G[1]), p[1] ^ mul(fb, G[2]), p[2] ^ mul(fb, G[3])]
    m3, m2, m1, m0 = msg
    return [p[0], p[1], p[2], p[3], m0, m1, m2, m3]


def syndromes(c):
    return [poly_eval(c, alpha(j)) for j in range(1, 5)]  # S1..S4


# ---------------------------------------------------------------- decoder
def berlekamp_massey(S):
    """Blahut's form, one iteration per clock in rs_bm.v. S = [S1, S2, S3, S4]."""
    lam = [1, 0, 0, 0, 0]
    b = [1, 0, 0, 0, 0]
    L = 0
    for r in range(1, 5):
        delta = 0
        for j in range(5):
            if 1 <= r - j <= 4:
                delta ^= mul(lam[j], S[r - j - 1])
        xb = [0] + b[:4]                           # x * B(x), truncated to degree 4
        new_lam = [lam[i] ^ mul(delta, xb[i]) for i in range(5)]
        if delta != 0 and 2 * L <= r - 1:
            dinv = inv(delta)
            b = [mul(dinv, c) for c in lam]
            L = r - L
        else:
            b = xb
        lam = new_lam
    return lam, L


def chien_forney(lam, L, S):
    """Returns (err_vals per position 0..7, root mask, fail)."""
    omega = [0] * 4
    for k in range(4):
        for j in range(k + 1):
            omega[k] ^= mul(lam[j], S[k - j])     # S[k-j] is S_{k-j+1}
    dlam = [lam[1], 0, lam[3], 0]                  # formal derivative, char 2: odd terms only
    errs = [0] * 8
    mask = 0
    bad = False
    for i in range(8):
        xinv = alpha(-i)
        if poly_eval(lam, xinv) == 0:
            mask |= 1 << i
            den = poly_eval(dlam, xinv)
            if den == 0:
                bad = True
            else:
                errs[i] = mul(poly_eval(omega, xinv), inv(den))
                if errs[i] == 0:
                    bad = True
    nroots = bin(mask).count("1")
    fail = bad or L > 2 or nroots != L
    return errs, mask, fail


def decode(r):
    """r = received codeword list c[0..7]. Returns (corrected, fixed_mask, nfixed, fail)."""
    S = syndromes(r)
    lam, L = berlekamp_massey(S)
    errs, mask, fail = chien_forney(lam, L, S)
    if fail:
        return list(r), 0, 0, True
    return [r[i] ^ errs[i] for i in range(8)], mask, bin(mask).count("1"), False


# ---------------------------------------------------------------- packing helpers
def word(c):
    return sum(c[i] << (4 * i) for i in range(8))


def msg16(msg):
    m3, m2, m1, m0 = msg
    return (m3 << 12) | (m2 << 8) | (m1 << 4) | m0


# ---------------------------------------------------------------- self-test
def self_test():
    # every codeword has zero syndromes; the code has minimum distance 5
    codewords = {}
    for m in range(1 << 16):
        msg = [(m >> 12) & 15, (m >> 8) & 15, (m >> 4) & 15, m & 15]
        c = encode(msg)
        assert syndromes(c) == [0, 0, 0, 0], msg
        codewords[m] = c
    rng = random.Random(1)
    sample = rng.sample(range(1 << 16), 400)
    for a, b in itertools.combinations(sample[:120], 2):
        d = sum(x != y for x, y in zip(codewords[a], codewords[b]))
        assert d >= 5, (a, b, d)
    # every 1- and 2-symbol error pattern is corrected exactly
    for m in sample[:60]:
        c = codewords[m]
        for n in (1, 2):
            for pos in itertools.combinations(range(8), n):
                for _ in range(8):
                    r = list(c)
                    for p in pos:
                        r[p] ^= rng.randrange(1, 16)
                    fixed, mask, nfixed, fail = decode(r)
                    assert not fail and fixed == c and nfixed == n, (m, pos, r)
                    assert mask == sum(1 << p for p in pos)
    # 3 errors are never silently returned as the right data, and never look clean
    for m in sample[:60]:
        c = codewords[m]
        for pos in itertools.combinations(range(8), 3):
            r = list(c)
            for p in pos:
                r[p] ^= rng.randrange(1, 16)
            fixed, mask, nfixed, fail = decode(r)
            assert syndromes(r) != [0, 0, 0, 0]
            assert fail or fixed != c
    print("self-test passed")


def write_vectors(path):
    """One line per case: msg[95:80] errpat[79:48] exp_word[47:16] fail[15:12] nfixed[11:8] mask[7:0]."""
    rng = random.Random(2026)
    msgs = [0x0000, 0xFFFF, 0x1234, 0xA5C3] + [rng.randrange(1 << 16) for _ in range(16)]
    lines = []
    for m in msgs:
        msg = [(m >> 12) & 15, (m >> 8) & 15, (m >> 4) & 15, m & 15]
        c = encode(msg)
        cases = [()]
        cases += [((p, e),) for p in range(8) for e in range(1, 16)]
        for pos in itertools.combinations(range(8), 2):
            for _ in range(4):
                cases.append(tuple((p, rng.randrange(1, 16)) for p in pos))
        for pos in itertools.combinations(range(8), 3):
            cases.append(tuple((p, rng.randrange(1, 16)) for p in pos))
        for case in cases:
            err = [0] * 8
            for p, e in case:
                err[p] = e
            r = [c[i] ^ err[i] for i in range(8)]
            fixed, mask, nfixed, fail = decode(r)
            lines.append(f"{m:04X}{word(err):08X}{word(fixed):08X}{int(fail):X}{nfixed:X}{mask:02X}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return len(lines)


if __name__ == "__main__":
    print("EXP  :", " ".join(f"{x:X}" for x in EXP[:15]))
    print("INV  :", " ".join("-" if a == 0 else f"{inv(a):X}" for a in range(16)))
    print("g(x) = x^4 + {:X}x^3 + {:X}x^2 + {:X}x + {:X}".format(G[3], G[2], G[1], G[0]))
    print("encode(1,2,3,4) =", " ".join(f"{s:X}" for s in reversed(encode([1, 2, 3, 4]))), "(c7..c0)")
    self_test()
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "..", "sim", "vectors.mem")
    n = write_vectors(out)
    print(f"wrote {n} vectors to {os.path.normpath(out)}")
