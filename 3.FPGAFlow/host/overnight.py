"""Overnight pipeline: finish the neuron-expansion study, analyze everything, put the best
models on the FPGA, and regenerate the portfolio media. Writes results/OVERNIGHT_STATUS.md.

  python host/overnight.py            (run from the project root; safe to re-run, finished jobs are skipped)
"""

import json
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

import numpy as np

PY = sys.executable
STATUS = Path("results/OVERNIGHT_STATUS.md")
LOG = Path("results/overnight.log")
steps = []


def log(msg: str):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(name: str, args: list[str], out: Path | None = None, timeout: float | None = None) -> bool:
    log(f"START {name}: {' '.join(args)}")
    t0 = time.time()
    try:
        with (out.open("w", encoding="utf-8") if out else open(LOG, "a", encoding="utf-8")) as f:
            r = subprocess.run(args, stdout=f, stderr=subprocess.STDOUT, timeout=timeout)
        ok = r.returncode == 0
    except Exception as e:  # noqa: BLE001
        log(f"  exception: {e}")
        ok = False
    dt = (time.time() - t0) / 60
    steps.append((name, ok, dt, str(out) if out else ""))
    log(f"{'OK' if ok else 'FAILED'} {name} ({dt:.1f} min)")
    write_status()
    return ok


def best_by_val(rows, pred):
    cands = [r for r in rows if pred(r)]
    return min(cands, key=lambda r: r["val_ler"]) if cands else None


def load_jsonl(p):
    p = Path(p)
    if not p.exists():
        return []
    return list({r["name"]: r for r in (json.loads(l) for l in p.read_text().splitlines() if l.strip())}.values())


def nexp_table() -> str:
    rows = load_jsonl("results/nexp.jsonl")
    g = defaultdict(list)
    for r in rows:
        g[(r["schedule"], "plain" if r.get("plain") else r["saliency"], r["n_sal"])].append(r)
    lines = ["| schedule | variant | salient n | seeds | test LER mean ± std | XNOR bits | dedicated neurons |",
             "|---|---|---|---|---|---|---|"]
    for key in sorted(g):
        v = np.array([r["test_ler"] for r in g[key]])
        sd = v.std(ddof=1) if len(v) > 1 else 0
        lines.append(f"| {key[0]} | {key[1]} | {key[2]} | {len(v)} | {v.mean():.5f} ± {sd:.5f} | "
                     f"{g[key][0]['xnor_bits']} | {g[key][0]['n_dedicated']} |")
    return "\n".join(lines)


def write_status(extra: str = ""):
    s = ["# Overnight run status", "", f"Last update: {time.strftime('%Y-%m-%d %H:%M:%S')}", "",
         "| step | result | minutes | output |", "|---|---|---|---|"]
    s += [f"| {n} | {'OK' if ok else '**FAILED**'} | {dt:.1f} | {o} |" for n, ok, dt, o in steps]
    hil_lines = []
    for p in sorted(Path("build").glob("*/hil_result.json")):
        h = json.loads(p.read_text())
        hil_lines.append(f"| {p.parent.name} | {h['shots']:,} | {h['mismatches_vs_golden']} | "
                         f"{h['fpga_ler']:.6f} | {h['pymatching_ler']:.6f} |")
    if hil_lines:
        s += ["", "## FPGA hardware tests", "", "| model | shots | mismatches vs golden | FPGA LER | PyMatching LER |",
              "|---|---|---|---|---|"] + hil_lines
    if Path("results/nexp.jsonl").exists():
        s += ["", "## Neuron-expansion study (results/nexp.jsonl)", "", nexp_table()]
    if extra:
        s += ["", extra]
    STATUS.write_text("\n".join(s) + "\n", encoding="utf-8")


def hil_model(label: str, ckpt: Path):
    out = Path("build") / ckpt.stem
    if not run(f"export {label}", [PY, "host/export.py", str(ckpt), "--out", str(out)],
               Path(f"results/export_{ckpt.stem}.log")):
        return
    run(f"FPGA test {label} (1M shots)", [PY, "host/hil.py", "--port", "COM10", "--model", str(out), "--n", "all",
                                          "--chunk", "1000"], Path(f"results/hil_full_{ckpt.stem}.log"),
        timeout=3 * 3600)


def main():
    log("overnight pipeline starting")
    write_status()
    try:
        done_logs = [str(p) for p in Path("results").glob("nexp_progress*.log")]
        run("neuron-expansion study (remaining jobs)",
            [PY, "host/run_jobs.py", "jobs/nexp.txt", "--parallel", "1", "--skip-done", *done_logs,
             "--logdir", "logs/nexp_overnight"], Path("results/nexp_progress_overnight.log"))
        run("analyze main study", [PY, "host/analyze_study.py"], Path("results/analysis_study.md"))

        study = load_jsonl("results/study.jsonl")
        w96 = best_by_val(study, lambda r: r["model"] == "expanded" and r["hidden"] == [96, 96] and r.get("k") == 3)
        if w96:
            hil_model("best 96-wide 3-bit-first-layer model", Path("models/study") / f"{w96['name']}.pt")

        nexp = load_jsonl("results/nexp.jsonl")
        best_n = best_by_val(nexp, lambda r: not r.get("plain"))
        if best_n:
            hil_model(f"best neuron-expansion model ({best_n['name']})", Path("models/nexp") / f"{best_n['name']}.pt")

        run("portfolio figures + summary.pdf", [PY, "host/make_figures.py"], Path("results/make_figures.log"))
    except Exception:  # noqa: BLE001
        log("pipeline error:\n" + traceback.format_exc())
    write_status("Pipeline finished." if all(ok for _, ok, _, _ in steps) else
                 "Pipeline finished with failures. See results/overnight.log and the per-step logs.")
    log("overnight pipeline finished")


if __name__ == "__main__":
    main()
