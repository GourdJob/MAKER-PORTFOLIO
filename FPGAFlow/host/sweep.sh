#!/usr/bin/env bash
# Phase 2 sweep at one physical error rate: teacher, plain BNN (3 seeds),
# expanded BNN over (s, k) with AWQ saliency, and the random-saliency ablation.
# Results append to results/results.jsonl; summarized with host/summarize.py.
#   bash host/sweep.sh data/d3_r3_p0.005.npz
set -euo pipefail
DATA=${1:-data/d3_r3_p0.005.npz}
T="python host/train.py --data $DATA"

$T --model fp
for seed in 0 1 2; do $T --model bnn --seed $seed; done
for k in 2 3; do
  for s in 0.01 0.05 0.1 0.2; do $T --model expanded --salient $s --k $k --saliency awq; done
done
for s in 0.05 0.1 0.2; do $T --model expanded --salient $s --k 2 --saliency random; done
for seed in 1 2; do $T --model expanded --salient 0.1 --k 2 --saliency awq --seed $seed; done
