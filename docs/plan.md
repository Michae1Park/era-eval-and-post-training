# Plan

**Eval-driven post-training** for the [equity-research-agent](https://github.com/Michae1Park/equity-research-agent) (ERA): measure the agent, diagnose why a small model fails, post-train against those failures, and verify the fix with the same harness.

```
 MEASURE ──► DIAGNOSE ──► FIX ──► VERIFY
    ▲                               │
    └──── same eval harness ────────┘
```

Measurement follows the agent's own pipeline, one stage at a time, then the whole:

```
 question ─► RETRIEVAL ─► GENERATION ─► TOOL USE ─► answer ─► JUDGE ─► end-to-end
   M1          M2           M3                     M4        M5
                                                     forecast ─► BACKTEST  M6
```

Questions are numbered by act (**M**easure, **D**iagnose, **F**ix, **V**erify, **S**tretch). Each is answered by one or more **evaluations** (`M1.1`, …): the data it consumes, the execution path it exercises, how it is scored, and a result with example cases. Full result tables go in [`results.md`](results.md), in the same order; run commands are in [`harness.md`](harness.md).

## Research questions

| Act | # | Question | Evaluations |
|---|---|---|---|
| Measure | M1 | Does retrieval return the right evidence? | M1.1 |
| Measure | M2 | Given the right evidence, is the answer faithful? | M2.1–M2.2 |
| Measure | M3 | Does the agent call the right tools, with the right args? | M3.1 |
| Measure | M4 | Can an LLM-judge panel be trusted for financial research output? | M4.1–M4.5 |
| Measure | M5 | How good and how reliable is the agent end to end (pass^k)? | M5.1–M5.2 |
| Measure | M6 | Do next-quarter forecasts beat a naive baseline, and when they miss, did consensus miss too? | M6.1–M6.3 |
| Diagnose | D1 | Which layer causes each failure, and how does that change with model size? | D1.1–D1.2 |
| Diagnose | D2 | Which knobs matter most? | D2.1–D2.4 |
| Fix | F1 | Can post-training aimed at diagnosed failures close the small-to-large gap? Which technique fixes which failure? | F1.1–F1.4 |
| Verify | V1 | Do gains hold on held-out data, without reward gaming or regressions? | V1.1–V1.7 |
| Stretch | S1 | Can a router plus a small model match a single large model? | S1.1 |

## Benchmark: ERA-Bench

Details in [`bench.md`](bench.md); counts in [`bench-coverage.md`](bench-coverage.md). Categories run from simple to complex:

| Category | Example task | Checked by |
|---|---|---|
| Factual lookup | `ask-uber-trips-2026q1`: How many trips did Uber report in Q1 2026? | Rule |
| Multi-hop / computation | `gen-yoy-abnb-operating_income-2026q1`: y/y change in Airbnb operating income | Rule |
| Comparative | `investigate-cart-dash-growth-valuation`: whose order value grew faster, and which is cheaper | Rule + judge |
| Synthesis / research | `research-abnb-variance-2026q2`: our Q2 estimate vs. actual, and why | Judge |
| Unanswerable | `ask-dash-our-price-target`, `adv-false-premise-cart-loss` | Rule + judge (abstain) |
| Adversarial | `gen-inject-override_value-dash`: injected instruction in a retrieved doc | Rule (canary) |

| Split | Tasks | Use |
|---|---|---|
| dev | 529 | Fix the agent against it |
| test | 875 | Report only |
| train | 1,263 | Post-training only; pre-2025Q3, TRIP and CART held out |

## Execution paths

What an evaluation isolates. "In situ" means the full agent runs and the stage is read from its trace.

| Path | What runs | What is held fixed |
|---|---|---|
| **RAG** | Query rewrite → hybrid search → rerank → top-K chunks | No LLM answer; scored against gold chunk ids |
| **Gen** | LLM answers from gold chunks only | Retrieval and tools bypassed |
| **Tools** | Agent loop: tool choice, args, step count | Read from trace; scored against expected trajectory |
| **E2E** | Whole agent: retrieval, tools, model, answer | Nothing |
| **Judge** | Judge panel scoring a fixed set of answers | Agent outputs frozen |
| **Backtest** | Agent's forecast pipeline, walk-forward | Inputs cut at each as-of date |

Status: ✅ real numbers · ⏳ pipeline built, not run · ⬜ not built.

## Act 1: Measure

### M1: Retrieval (L1)

| ID | Evaluation | Inputs | Path | Metric | Result |
|---|---|---|---|---|---|
| M1.1 | Retrieval in isolation | 163 dev tasks with gold `chunk_ids` | RAG | hit@k, recall@k, MRR, nDCG@8 | ✅ hit@8 0.69 [0.61–0.76], hit@1 0.25, MRR 0.38 |

| Case | Task | Result | Read |
|---|---|---|---|
| ✅ Strong | Guidance (n=31) | hit@8 0.84 | |
| ⚠️ Low rank | `ask-dash-revenue-adj-ebitda-2026q2` | Hit at rank 7, recall 1/4 | Reranker underweights the table chunk |
| ❌ Wrong quarter | `ask-cart-revenue-adj-ebitda-2025q4` | 0/8; top hits are CART 2025Q1/Q3 releases | Period filter not applied |
| ❌ Wrong document | `ask-bkng-net-income-2026q2` | 0/8; right quarter, but 10-Q (`I.1`) chunks instead of the release | Known gold limitation (see Limitations) |
| ❌ Weak categories | `unit_handling` 0.44, `reported_financials` 0.56, `operating_kpis` 0.57 | | Table-heavy chunks rank poorly |

### M2: Generation (L2)

| ID | Evaluation | Inputs | Path | Metric | Result |
|---|---|---|---|---|---|
| M2.1 | Given gold context | Dev tasks with `generation` layer | Gen | Rule-scored faithfulness | ⏳ |
| M2.2 | In situ | Same tasks, full pipeline | E2E | Faithfulness; gap vs. M2.1 = loss from retrieval | ⏳ |

### M3: Tool use (L3)

| ID | Evaluation | Inputs | Path | Metric | Result |
|---|---|---|---|---|---|
| M3.1 | Trajectory failures | Dev tasks with `trajectory` gold | Tools | T1–T8 rates, step efficiency | ⏳ |

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

### M4: Judge trustworthiness

Validated before any judge-scored end-to-end number is reported.

| ID | Evaluation | Inputs | Path | Metric | Result |
|---|---|---|---|---|---|
| M4.1 | Judge vs. human | ~150 human-labeled answers (`eval/judge/human.jsonl`) | Judge | Cohen's κ per dimension | ⏳ |
| M4.2 | Judge vs. judge | Baseline-27B dev answers | Judge | Krippendorff's α | ⏳ |
| M4.3 | Position / verbosity bias | Same answers, swapped order; length-varied | Judge | Win-rate shift; length–tone corr. | ⏳ |
| M4.4 | Self-preference | Answers from Qwen and Gemma runs; Qwen probe judge | Judge | Own-family score Δ | ⏳ |
| M4.5 | Consistency | Same answers re-scored | Judge | Repeat agreement | ⏳ |

Panel: gpt-oss-20b, Gemma-4-31B, Phi-4 (three families, served locally; Qwen only as a probe). Majority vote per point and dimension.

| Dimension | Priority | Scored by |
|---|---|---|
| Numeric accuracy | Critical | Rule (tolerance match) |
| Groundedness | Critical | Rule (cited chunk exists) + judge (supports claim) |
| Completeness | High | Judge rubric vs. gold key points |
| Finance safety | Medium | Rule + judge (no price targets or advice, abstains, resists injection) |
| Tone | Low | Judge |

### M5: End to end (L4)

| ID | Evaluation | Inputs | Path | Metric | Result |
|---|---|---|---|---|---|
| M5.1 | Answer quality | Full dev, Qwen3.6-27B | E2E + Judge | Correctness, groundedness, completeness, safety, tone | ⏳ |
| M5.2 | Reliability | Full dev, k=4 | E2E | pass@1, pass^k | ⏳ |

### M6: Forecast accuracy (L5)

| ID | Evaluation | Inputs | Path | Metric | Result |
|---|---|---|---|---|---|
| M6.1 | Forecast vs. naive, `defaults` proposer | 8 companies, releases 2024Q4–2026Q1; first-reported SEC actuals | Backtest | MdAPE, beats-naive rate, Wilcoxon | ✅ Revenue 2.6% vs. 2.9% (p 0.18); KPI 1.3% vs. 1.2%; EPS 45.9% vs. 77.9% (p<0.001) |
| M6.2 | EPS vs. consensus | Same, plus Alpha Vantage pre-print EPS; 23/47 same-basis quarters | Backtest | MdAPE, miss quadrants | ✅ 24.3% vs. 22.2% (p 0.71); agent closer 10/23 |
| M6.3 | Forecast vs. naive, `llm` proposer | Same as M6.1 | Backtest + LLM | Same as M6.1–M6.2 | ⏳ |

Leakage guard: every input filed before the as-of, target quarter not in history, scorer rejects forecasts dated after the print.

| Case | Ticker / quarter | Actual | Agent | Consensus | Read |
|---|---|---|---|---|---|
| ✅ Both close | ABNB 2025Q3 EPS | 2.21 | 2.03 | 2.32 | 8% vs. 5% APE |
| ✅ Beat the Street | CART 2025Q3 EPS | 0.51 | 0.53 | 0.79 | 4% vs. 55% APE |
| ❌ Agent-only miss | CART 2025Q2 EPS | 0.41 | 0.26 | 0.39 | 36% vs. 5% APE |
| ❌ Agent-only miss | ABNB 2025Q1 EPS | 0.24 | −0.12 | 0.24 | Wrong sign; Street exact |

## Act 2: Diagnose

The output is a ranked list of small-model failure modes, which becomes Act 3's target list.

### D1: Root cause and model size

| ID | Evaluation | Inputs | Path | Metric | Result |
|---|---|---|---|---|---|
| D1.1 | Root-cause attribution | Failed runs from M5.1 | RAG → Tools → Gen | Share by first failing layer | ⏳ |
| D1.2 | Model swap | 158-task stratified dev subset: Qwen3.6-27B, Gemma-4-31B, Qwen3.5-9B (k=4), Qwen3-1.7B | E2E | Quality, pass^k, T1–T8 and root cause by size; latency, tokens | ⏳ |

The largest local models stand in for frontier.

### D2: Knobs

All on the 158-task subset, Δ vs. the 27B baseline.

| ID | Knob | Values | Path | Metric | Result |
|---|---|---|---|---|---|
| D2.1 | Top-K | 4 / 8 / 16 | E2E | Δ quality, latency | ⏳ |
| D2.2 | Reranker | on / off | E2E | Δ quality, latency | ⏳ |
| D2.3 | Max tool calls | 8 / 20 | E2E | Δ quality; T7/T8 shift | ⏳ |
| D2.4 | Temperature | 0 / 0.7 | E2E | Δ quality; pass^k shift | ⏳ |

Chunk size is out of scope (one chunking build).

## Act 3: Fix

### F1: Targeted post-training

Ordered from the cheapest signal to the richest:

| ID | Target failure | Technique | Training data (from evals) | Model | Measured by | Result |
|---|---|---|---|---|---|---|
| F1.1 | T1–T4 (format, tool, args) | SFT | 27B trajectories on train prompts passing all L3 rule checks | 7–8B LoRA | M3.1, M5.1 | ⬜ |
| F1.2 | T5–T6 (hallucination, ignoring output) | DPO | Judge-ranked grounded vs. unsupported answer pairs | 7–8B LoRA | M2.2, groundedness | ⬜ |
| F1.3 | Numeric errors, T7–T8 | GRPO | Rule rewards on XBRL train tasks: number matches gold, valid calls, step penalty | 3–4B LoRA + vLLM | Numeric acc., T7–T8 | ⬜ |
| F1.4 | Forecast misses (stretch) | GRPO | Proposer assumptions rewarded by realized backtest error, quarters before 2025Q3 | 3–4B | M6.1–M6.2 | ⬜ |

Each stage is compared with the previous one on dev: paired Δ with bootstrap CI, McNemar, fixed / broken task lists. Hardware: a single L40S (48 GB).

## Act 4: Verify

### V1: The fix is real (test split)

| ID | Check | Inputs | Path | Metric | Result |
|---|---|---|---|---|---|
| V1.1 | Held-out companies | Test tasks tagged `holdout_company` (TRIP, CART) | E2E | Quality before vs. after | ⬜ |
| V1.2 | Held-out task types | Test categories absent from train | E2E | Same | ⬜ |
| V1.3 | Regressions | Safety, abstention, injection, tone tasks | E2E + Judge | Before vs. after | ⬜ |
| V1.4 | Reliability | Test, k=5 | E2E | pass^k before vs. after | ⬜ |
| V1.5 | Reward gaming | GRPO model outputs | E2E + Judge | Rule reward vs. judge score correlation | ⬜ |
| V1.6 | Judge circularity | DPO model outputs | Judge (outside panel) | Score vs. panel score | ⬜ |
| V1.7 | Forecast | M6.3 rerun on post-trained proposer | Backtest | MdAPE vs. naive and consensus don't regress | ⬜ |

## Stretch

### S1: Router

| ID | Evaluation | Inputs | Path | Metric | Result |
|---|---|---|---|---|---|
| S1.1 | Difficulty router (lookups → small, synthesis → large) | Test | E2E | Quality and latency vs. small-only and large-only | ⬜ |

## Limitations

- Human labels come from a single annotator.
- Coverage is limited to US companies and SEC filings.
- Judge families overlap with the evaluated models.
- L1 gold covers earnings-release chunks only, so hits on the same figure in a 10-Q count as misses; hit@k is the headline.
- Gemma-4 is both a judge and a swapped model; its self-preference on its own run is not corrected.
- Free consensus covers EPS only, and its basis (GAAP vs. adjusted, split-adjusted) varies; mismatched quarters are excluded, which halves the sample.

## Roadmap

- [x] P1 Measure: retrieval baseline (M1.1)
- [x] P1 Measure: forecast backtest, defaults proposer (M6.1–M6.2)
- [ ] P1 Measure: generation, tool use, judges, end to end (M2–M5), LLM proposer (M6.3)
- [ ] P2 Diagnose: root cause, model swaps, knobs (D1–D2)
- [ ] P3 Fix: SFT → DPO → GRPO (F1)
- [ ] P4 Verify: held-out, regressions, reward gaming, judge circularity (V1)
- [ ] P5 Stretch: router (S1)
