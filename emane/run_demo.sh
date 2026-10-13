#!/usr/bin/env bash
# Part 2 end to end: schedule -> EMANE -> packets -> verdict, in one command.
#
#   emane/run_demo.sh [COORDS_JSON]        (default: examples/grid_16.json)
#
# Requires: Docker, and this package installed on the host (pip install -e .).
# Environment overrides:
#   EMANE_IMAGE      EMANE image to use        (default lbitnetemu/emane:1.5.2)
#   DURATION         seconds of traffic per run (default 20)
#   SLOTS_US         slot lengths to test       (default "1000 4000")
#   DOCKER_RT_FLAGS  extra docker flags for realtime scheduling, e.g.
#                    "--cpu-rt-runtime=850000" on cgroup-v1 hosts with RT group scheduling
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INPUT="${1:-$ROOT/examples/grid_16.json}"
IMAGE="${EMANE_IMAGE:-lbitnetemu/emane:1.5.2}"
DURATION="${DURATION:-20}"
SLOTS_US="${SLOTS_US:-1000 4000}"
NAME="$(basename "$INPUT" .json)"
OUT="$ROOT/emane/results/$NAME"

command -v tdma-emane-scenario >/dev/null || {
    echo "tdma-emane-scenario not found: run 'pip install -e .' in the repo first" >&2; exit 2; }
command -v docker >/dev/null || { echo "docker not found" >&2; exit 2; }

echo "== 1/3  Generating EMANE scenarios from $INPUT"
rm -rf "$OUT"
RUNS=()
for us in $SLOTS_US; do
    label="slot-$((us / 1000))ms"
    [[ $((us % 1000)) -ne 0 ]] && label="slot-${us}us"
    tdma-emane-scenario --input "$INPUT" --out "$OUT/$label" --slot-us "$us"
    RUNS+=("results/$NAME/$label/optimized" "results/$NAME/$label/control-g-only")
done

echo "== 2/3  Running EMANE ($IMAGE), ${DURATION}s of traffic per run"
# shellcheck disable=SC2086
docker run --rm --privileged ${DOCKER_RT_FLAGS:-} \
    -v "$ROOT/emane:/work" --entrypoint bash "$IMAGE" -c "
        set -e
        for run in ${RUNS[*]}; do
            python3 /work/run_experiment.py /work/\$run --duration $DURATION
        done
        chown -R $(id -u):$(id -g) /work/results"

echo "== 3/3  Comparing measured delivery with the prediction"
SCEN_DIRS=()
for run in "${RUNS[@]}"; do SCEN_DIRS+=("$ROOT/emane/$run"); done
python3 "$ROOT/emane/analyze.py" "${SCEN_DIRS[@]}" --markdown "$OUT/summary.md" | tee "$OUT/summary.txt"
