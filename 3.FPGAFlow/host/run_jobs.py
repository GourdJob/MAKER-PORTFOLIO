"""Run a queue of shell commands N at a time (one command per line, '#' = comment).

  python host/run_jobs.py jobs/pilot.txt --parallel 3

Each job's output goes to <logdir>/<job-number>.log. A failed job is reported but does not
stop the queue. Lines starting with 'WAIT' act as a barrier (wait for all running jobs),
e.g. to train teachers before the students that need them.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs", type=Path)
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--logdir", type=Path, default=None, help="default: logs/<jobs-file-stem>")
    ap.add_argument("--skip-done", type=Path, nargs="*", default=[],
                    help="progress logs of earlier runs; commands they report as 'ok' are skipped")
    args = ap.parse_args()

    done_cmds = set()
    for log in args.skip_done:
        for l in log.read_text().splitlines():
            if " ok: " in l:
                done_cmds.add(l.split(" ok: ", 1)[1].strip())

    lines = [l.strip() for l in args.jobs.read_text().splitlines()]
    lines = [l for l in lines if l and not l.startswith("#")]
    n_skip = sum(1 for l in lines if l in done_cmds)
    lines = [l for l in lines if l not in done_cmds]
    if n_skip:
        print(f"skipping {n_skip} jobs already completed", flush=True)
    logdir = args.logdir or Path("logs") / args.jobs.stem
    logdir.mkdir(parents=True, exist_ok=True)

    n_jobs = sum(1 for l in lines if l != "WAIT")
    running, done, failed, idx = [], 0, [], 0
    t0 = time.time()

    def reap(block_all: bool):
        nonlocal done
        while running and (block_all or len(running) >= args.parallel):
            for job in list(running):
                num, cmd, proc, f = job
                if proc.poll() is not None:
                    f.close()
                    running.remove(job)
                    done += 1
                    if proc.returncode != 0:
                        failed.append((num, cmd))
                    status = "ok" if proc.returncode == 0 else f"FAILED ({proc.returncode})"
                    print(f"[{done}/{n_jobs} {(time.time() - t0) / 60:5.1f} min] #{num} {status}: {cmd}",
                          flush=True)
            time.sleep(1)

    for line in lines:
        if line == "WAIT":
            reap(block_all=True)
            continue
        reap(block_all=False)
        idx += 1
        f = open(logdir / f"{idx:03d}.log", "w")
        f.write(f"$ {line}\n")
        f.flush()
        running.append((idx, line, subprocess.Popen(line, shell=True, stdout=f, stderr=subprocess.STDOUT), f))
    reap(block_all=True)

    print(f"finished {n_jobs} jobs in {(time.time() - t0) / 60:.1f} min, {len(failed)} failed")
    for num, cmd in failed:
        print(f"  FAILED #{num}: {cmd}   (log: {logdir / f'{num:03d}.log'})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
