#!/usr/bin/env bash
set -euo pipefail
preset=${1:?usage: eval/serve.sh <preset> [port]}
port=${2:-8002}
here=$(cd "$(dirname "$0")/.." && pwd)
agent=$here/../equity-research-agent
VLLM_BIN=${VLLM_BIN:-$(command -v vllm || echo ~/miniconda3/envs/vllm_py311/bin/vllm)}
cpus=$(sed -n 's/^ERA_CPUSET=//p' "$agent/.env" 2>/dev/null || true)
pin=(); [[ -n "$cpus" ]] && pin=(taskset -c "$cpus")
case "$preset" in
  phi-4)
    exec "${pin[@]}" "$VLLM_BIN" serve microsoft/phi-4 --port "$port" --gpu-memory-utilization 0.9 \
      --max-model-len 16384 --enable-prefix-caching ;;
  *)
    PORT=$port JUDGE_PORT=$port JUDGE_GPU_UTIL=0.9 exec "$agent/scripts/serve_vllm.sh" "$preset" ;;
esac
