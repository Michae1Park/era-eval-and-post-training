# Harness and scoring

```bash
uv sync
uv run python eval/bench/src/build.py ../equity-research-agent
uv run python eval/harness/run.py --label v1-<commit> --split dev --k 4
uv run python eval/scoring/score.py results/v1-<commit>/dev
uv run python eval/scoring/compare.py results/v1-<commit>/dev results/v2-<commit>/dev
```

| Part | Behavior |
|---|---|
| Agents | Any agent behind `AgentUnderTest` (`eval/harness/agents/`); ERA is `agents/era.py` |
| Config | `eval/harness/config.yaml` pins model, budgets, search, timeouts, retries |
| Runtime | Per-task deadline checked at every model and tool call; transient errors retried with backoff; SIGINT/SIGTERM stop cleanly |
| Errors | `agent_error`, `timeout` count against the agent; `harness_error`, `infra_error` are rerun on resume and never scored |
| Traces | One JSON trace per run (turns, tool calls, args, results, tokens, timing, agent commit, bench hash); registry in `results/runs.jsonl` |
| Injection | Tools are wrapped to plant the payload |
| Rule checks | Numbers within tolerance, model-cell refs, abstention, canaries, cited-number faithfulness, required, ordered and forbidden tools, repeats, tool errors, budget |
| Stats | pass@1 with 95% CI (Wilson for k=1, task bootstrap for k>1); pass^k by mode, category, held-out company |
| Compare | Paired delta with bootstrap CI, McNemar exact test, fixed and broken task lists |
