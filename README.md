# era-eval-and-post-training

Eval-driven post-training for the [equity-research-agent](https://github.com/Michae1Park/equity-research-agent): measure, diagnose, post-train against diagnosed failures, verify.

| Doc | Contents |
|---|---|
| [`docs/plan.md`](docs/plan.md) | What we intend to do: RQs, benchmark, methods, techniques |
| [`docs/results.md`](docs/results.md) | Result tables, in order |
| [`docs/bench.md`](docs/bench.md) | ERA-Bench sources, splits, schema |
| [`docs/bench-coverage.md`](docs/bench-coverage.md) | Generated bench counts |
| [`docs/harness.md`](docs/harness.md) | Running the harness and scoring |

```
eval/       bench, harness, scoring (never imports training/)
training/   trajectory export, SFT → DPO → GRPO
results/    run traces, scores, comparisons
docs/
```
