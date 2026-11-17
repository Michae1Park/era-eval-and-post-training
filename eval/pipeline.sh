#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
AGENT=$ROOT/../equity-research-agent
LOGS=$ROOT/results/logs
mkdir -p "$LOGS"
SUBSET=$(tr '\n' ' ' < eval/bench/tasks/dev-subset.txt)
CPUS=$(sed -n 's/^ERA_CPUSET=//p' "$AGENT/.env" 2>/dev/null || echo 16-31)
PY=(taskset -c "$CPUS" uv run python)
ONLY=${ONLY:-all}
SERVER=

log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOGS/pipeline.log"; }

wait_gpu() {
  while [[ -n $(nvidia-smi --query-compute-apps=pid --format=csv,noheader) ]]; do
    log "GPU busy ($(nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader | tr '\n' ' ')); waiting"
    sleep 600
  done
}

serve() {
  local preset=$1 port=$2
  wait_gpu
  log "serving $preset on :$port"
  setsid "$ROOT/eval/serve.sh" "$preset" "$port" > "$LOGS/serve-$preset.log" 2>&1 &
  SERVER=$!
  for _ in $(seq 180); do
    curl -sf "http://localhost:$port/v1/models" > /dev/null && { log "$preset ready"; return 0; }
    kill -0 "$SERVER" 2> /dev/null || { log "$preset failed to start, see serve-$preset.log"; return 1; }
    sleep 10
  done
  log "$preset not ready after 30 min"; stop; return 1
}

stop() {
  [[ -n "$SERVER" ]] && kill -- -"$SERVER" 2> /dev/null
  wait "$SERVER" 2> /dev/null
  SERVER=
  sleep 20
}

harness() {
  local label=$1; shift
  log "harness $label $*"
  "${PY[@]}" eval/harness/run.py --label "$label" --split dev "$@" >> "$LOGS/$label.log" 2>&1
  "${PY[@]}" eval/scoring/score.py "results/$label/dev" >> "$LOGS/$label.log" 2>&1
}

on_subset() { harness "$@" --ids $SUBSET; }

stage() { [[ "$ONLY" == all || " $ONLY " == *" $1 "* ]]; }

if stage agent; then
  serve qwen3.6-27b-fp8 8001 && {
    harness baseline-27b --k 4
    "${PY[@]}" eval/scoring/generation.py --label baseline-27b >> "$LOGS/baseline-27b.log" 2>&1
    on_subset abl-topk4 --set retrieval_overrides.k=4
    on_subset abl-topk16 --set retrieval_overrides.k=16
    on_subset abl-norerank --set retrieval_overrides.reranker=none
    on_subset abl-calls8 --set agent.max_calls=8
    on_subset abl-temp07 --set generation.temperature=0.7
    "${PY[@]}" eval/judge/judge.py results/baseline-27b/dev --self-preference --judges qwen >> "$LOGS/judge.log" 2>&1
    "${PY[@]}" eval/forecast/backtest.py --label proposer-llm --proposer llm >> "$LOGS/forecast.log" 2>&1 \
      && uv run python eval/forecast/score.py --label proposer-llm >> "$LOGS/forecast.log" 2>&1
    stop
  }
fi

if stage swaps; then
  serve qwen3.5-9b 8001 && {
    on_subset swap-9b --k 4 --set generation.model=openai:Qwen/Qwen3.5-9B
    "${PY[@]}" eval/scoring/generation.py --label swap-9b --set generation.model=openai:Qwen/Qwen3.5-9B >> "$LOGS/swap-9b.log" 2>&1
    stop
  }
  serve qwen3-1.7b 8001 && { on_subset swap-1.7b --set generation.model=openai:Qwen/Qwen3-1.7B; stop; }
  serve gemma-4-31b-fp8 8001 && { on_subset swap-gemma31b --set generation.model=openai:RedHatAI/gemma-4-31B-it-FP8-block; stop; }
fi

RUNS=$(ls -d results/*/dev 2> /dev/null | grep -v -e forecast -e retrieval)

if stage judges; then
  for judge in gpt-oss:gpt-oss-20b gemma:gemma-4-31b-fp8 phi:phi-4; do
    serve "${judge#*:}" 8002 && {
      for run in $RUNS; do
        [[ -f $run/scores.jsonl ]] && "${PY[@]}" eval/judge/judge.py "$run" --judges "${judge%%:*}" >> "$LOGS/judge.log" 2>&1
      done
      stop
    }
  done
fi

if stage report; then
  for run in $RUNS; do
    [[ -f $run/scores.jsonl ]] || continue
    extra=(); [[ $run == results/baseline-27b/dev ]] && extra=(--self-preference)
    "${PY[@]}" eval/judge/judge.py "$run" "${extra[@]}" >> "$LOGS/judge.log" 2>&1
    "${PY[@]}" eval/scoring/taxonomy.py "$run" >> "$LOGS/report.log" 2>&1
  done
  "${PY[@]}" eval/judge/agreement.py results/baseline-27b/dev >> "$LOGS/report.log" 2>&1
  for run in $RUNS; do
    [[ $run != results/baseline-27b/dev && -f $run/scores.jsonl ]] && \
      "${PY[@]}" eval/scoring/compare.py results/baseline-27b/dev "$run" >> "$LOGS/report.log" 2>&1
  done
  "${PY[@]}" eval/report.py >> "$LOGS/report.log" 2>&1
fi
log "pipeline done ($ONLY)"
