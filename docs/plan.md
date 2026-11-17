# Plan

**Eval-driven post-training** for the [equity-research-agent](https://github.com/Michae1Park/equity-research-agent) (ERA): measure the agent, diagnose why a small model fails, post-train against those failures, and verify the fix with the same harness.

```
 MEASURE ──► DIAGNOSE ──► FIX ──► VERIFY
    ▲                               │
    └──── same eval harness ────────┘
```

Results go in [`results.md`](results.md), in the same order as this plan.

## Research questions

| Act | # | Question |
|---|---|---|
| Measure | RQ1 | Can an LLM-judge panel be trusted for financial research output? |
| Measure | RQ9 | Do the agent's next-quarter forecasts beat a naive baseline, and when they miss, did consensus miss too? |
| Diagnose | RQ2 | Where does the agent fail (retrieval, tool use, generation), and how does that differ by model size? |
| Diagnose | RQ3 | How reliable is it across repeated runs (pass^k)? |
| Diagnose | RQ4 | Which knobs matter most? |
| Diagnose | RQ5 | What is the quality vs. cost/latency Pareto frontier? |
| Fix | RQ6 | Can post-training aimed at diagnosed failures close the small-to-frontier gap? Which technique fixes which failure? |
| Verify | RQ7 | Do gains hold on held-out data, without reward gaming or regressions? |
| Stretch | RQ8 | Can a router plus small models match a single large model? |

## Benchmark: ERA-Bench

Details in [`bench.md`](bench.md); counts in [`bench-coverage.md`](bench-coverage.md).

| Category | Example | Checked by |
|---|---|---|
| Factual lookup | Uber revenue Q2 2026 | Rule |
| Multi-hop / computation | Lyft adj. EBITDA margin on gross bookings | Rule |
| Comparative | Booking vs. Expedia room-night growth, and why | Rule + judge |
| Synthesis / research | Our Q3 2026 Uber forecast vs. guidance | Judge |
| Unanswerable | Netflix price target | Rule + judge (abstain) |
| Adversarial | Injected instruction in a retrieved doc | Rule (canary) |

| Split | Tasks | Use |
|---|---|---|
| dev | 529 | Fix the agent against it |
| test | 875 | Report only |
| train | 1,263 | Post-training only; pre-2025Q3, TRIP and CART held out |

## Act 1: Measure (RQ1)

**Layered evaluation.** Each layer is scored in isolation (e.g. L2 is given gold context) and in situ.

| Layer | Metrics |
|---|---|
| L1 Retrieval | Recall@K, MRR, nDCG@K |
| L2 Generation | Faithfulness given gold context |
| L3 Trajectory | Failure taxonomy (T1–T8), step efficiency |
| L4 End-to-end | Correctness, groundedness, completeness, safety, pass^k |
| L5 Forecast accuracy | Next-quarter forecast vs. reported actuals (MdAPE, beats-naive rate); EPS vs. consensus |

| Dimension | Priority | Method |
|---|---|---|
| Numeric accuracy | Critical | Rule (tolerance match) |
| Groundedness | Critical | Rule (cited chunk exists) + judge (supports claim) |
| Completeness | High | Judge rubric vs. gold key points |
| Finance safety | Medium | Rule + judge (no price targets or advice, abstains, resists injection) |
| Tone | Low | Judge |

**Forecast accuracy (L5).** Walk-forward backtest that reuses the agent's own (`era_agent.evaluation.backtest`): forecast the next quarter the day after each release, score against the first-reported SEC value. The agent's leakage probe (every input filed before the as-of; target quarter not in history) stops the run on failure, and the scorer also refuses any forecast dated after the print. Baseline: seasonal naive. EPS is also compared with pre-print consensus (Alpha Vantage), scored on the same GAAP actual, as a diagnostic: when the agent misses, did the Street miss too?

**Judges.** A 3-judge panel of open models from different families, served locally (gpt-oss-20b, Gemma-4-31B, Phi-4; none is the agent's Qwen, which runs only as a self-preference probe), anchored to ~150 human-labeled outputs. Checks: agreement with humans and between judges, position bias, verbosity bias, self-preference, and consistency.

## Act 2: Diagnose (RQ2–RQ5)

The output is a ranked list of small-model failure modes, which becomes Act 3's target list.

| Code | Failure mode | Detection |
|---|---|---|
| T1 | No tool call; parametric answer | Rule |
| T2 | Nonexistent tool | Rule |
| T3 | Wrong valid tool | Rule vs. expected trajectory |
| T4 | Malformed or incorrect args | Schema + rule |
| T5 | Empty tool result, hallucinates anyway | Rule + judge |
| T6 | Contradicts or ignores tool output | Judge |
| T7 | Loops / exceeds step budget | Rule |
| T8 | Premature termination | Rule |

- **Attribution:** each failed task is assigned a root layer: retrieval miss → tool error → reasoning error.
- **Reliability:** pass@1 and pass^{3,5,8} per model.
- **Knobs:** top-K (4/8/16), reranker on/off, max tool calls (8/20), temperature (0/0.7), on a stratified 158-task dev subset. Chunk size is out: the corpus has one chunking build.
- **Pareto:** no API models, so the largest local models stand in for frontier: Qwen3.6-27B (baseline, full dev, k=4), Gemma-4-31B, Qwen3.5-9B (k=4) and Qwen3-1.7B on the subset; quality, pass^k, GPU $, latency and tokens.

## Act 3: Fix (RQ6)

| Target failure | Technique | Training signal from evals |
|---|---|---|
| T1–T4 (format, tool, args) | SFT | Frontier trajectories passing all L3 rule checks |
| T5–T6 (hallucination, ignoring output) | DPO | Judge-ranked grounded vs. unsupported pairs |
| Numeric errors, T7–T8 | GRPO | Rule rewards: number matches gold, valid calls, step penalty |
| Forecast misses (L5 agent-only) | GRPO (stretch) | LLM proposer's assumptions rewarded by realized backtest error; train on quarters before 2025Q3 only |

| Technique | Model | Method |
|---|---|---|
| SFT, DPO | 7–8B | LoRA |
| GRPO | 3–4B (7–8B if it scales) | LoRA + vLLM rollouts |

Hardware: a single L40S (48 GB).

## Act 4: Verify (RQ7)

| Check | Method |
|---|---|
| Generalization | Held-out companies (TRIP, CART) and task types |
| Reward gaming | GRPO rule reward vs. judge score |
| Regressions | Safety, abstention and tone don't drop |
| Judge circularity | DPO model scored by a judge outside the training panel |
| Reliability | pass^k before vs. after |
| Cost | New point on the Pareto chart |
| Forecast accuracy | L5 rerun with `--proposer llm`: MdAPE vs. naive and EPS vs. consensus don't regress |

## Stretch (RQ8)

A difficulty classifier routes lookups to the small model and synthesis to the frontier model.

## Limitations

- Human labels come from a single annotator.
- Coverage is limited to US companies and SEC filings.
- Judge families overlap with the evaluated models.
- Costs reflect API prices at run time.
- L1 gold covers earnings-release chunks only, so hits on the same figure in a 10-Q count as misses; hit@k is the headline.
- Gemma-4 is both a judge and a swapped model; its self-preference on its own run is not corrected.
- Free consensus covers EPS only, and its basis (GAAP vs. adjusted, split-adjusted) varies; mismatched quarters are excluded, which halves the sample.

## Roadmap

- [ ] P1 Measure: bench, harness (L1–L4), judge validation
- [x] P1 Measure: L5 forecast accuracy backtest, defaults proposer
- [ ] P1 Measure: L5 with the LLM proposer
- [ ] P2 Diagnose: model swaps, taxonomy, pass^k, ablations, Pareto
- [ ] P3 Fix: SFT → DPO → GRPO
- [ ] P4 Verify: held-out, reward gaming, regressions, judge circularity
- [ ] P5 Stretch: router, robustness
