# era-eval-and-post-training

Systematically evaluate, diagnose, and improve AI systems through component-level testing, end-to-end benchmarking, inference optimization, and model post-training.

> **Status: mock draft.** Every number below is a placeholder (`x.xx`). This document sketches the story, the experiments, and the expected artifacts before running anything.

---

## TL;DR

We build **ERA-Bench**, a benchmark for the [equity-research-agent](https://github.com/Michae1Park/equity-research-agent) (ERA), a tool-using RAG agent that answers questions about public companies. Then we use it to answer one question:

> **How small a model can run a reliable financial research agent, and what does it take to get there?**

| Headline result (placeholder) | |
|---|---|
| Frontier model, end-to-end quality | `x.xx` |
| Small model (8B), baseline | `x.xx` |
| Small model + SFT + DPO + GRPO | `x.xx` (**`xx%` of frontier quality at `x%` of the cost**) |
| Judge panel agreement with human labels (Cohen's κ) | `x.xx` |

---

## 1. Motivation

Agent demos look good. Agent *evaluation* rarely holds up to scrutiny:

1. **Single-number scores hide where it fails.** A wrong answer can come from retrieval, tool use, or reasoning, and each one needs a different fix.
2. **LLM judges are used without being validated.** Their agreement with humans, biases, and consistency are rarely reported.
3. **Averages hide unreliability.** An agent that is right 80% of the time but rarely right on *every* attempt cannot be deployed.
4. **Finance is unforgiving.** A single fabricated number makes a report worthless.

This repo treats the ERA as the system under test and evaluates it **layer by layer**, **validates its own judges**, measures **reliability** as well as accuracy, and then uses the eval signals as **training signal** for small models.

## 2. Research Questions

| # | Question | Section |
|---|---|---|
| **RQ1** | Where does the agent fail: retrieval, tool use, or generation? | §5 |
| **RQ2** | Can an LLM-judge panel be trusted for financial research output? | §4 |
| **RQ3** | How reliable is the agent across repeated runs (pass^k)? | §5.4 |
| **RQ4** | Which knobs (retrieval K, chunking, temperature, step budget) matter most? | §6 |
| **RQ5** | What is the quality vs. cost/latency Pareto frontier across models? | §7 |
| **RQ6** | How much of the gap between small and frontier models can post-training close, and which technique helps most? | §8 |
| **RQ7** *(stretch)* | Can a router plus small models match a single large model? | §9 |

## 3. ERA-Bench: The Benchmark

### 3.1 Task Taxonomy

| Category | Example | Ground truth | Checked by |
|---|---|---|---|
| **Factual lookup** | "What was AAPL's FY2024 gross margin?" | Exact value from filing | Rule |
| **Multi-hop / computation** | "How did NVDA's R&D as % of revenue change from FY22 to FY24?" | Computed value | Rule |
| **Comparative analysis** | "Compare MSFT and GOOGL cloud segment growth." | Key facts + rubric | Rule + judge |
| **Synthesis / research** | "Summarize the main risks in TSLA's latest 10-K." | Gold key points | Judge |
| **Unanswerable / out-of-scope** | "What will AAPL stock be next month?" | Should abstain | Rule + judge |
| **Adversarial** | Retrieved doc contains an injected instruction | Should ignore it | Rule |

### 3.2 Dataset Stats (placeholder)

| Split | # tasks | # companies | Answers checkable by rule |
|---|---|---|---|
| dev | `xxx` | `xx` | `xx%` |
| test | `xxx` | `xx` | `xx%` |
| train (post-training only) | `x,xxx` | `xx` | `xx%` |

Each task includes the question, the gold answer and/or key points, **gold evidence chunks** (for retrieval metrics), and the **expected tool trajectory** (for trajectory metrics).

## 4. Evaluation Methodology

### 4.1 Layered Evaluation

```
┌───────────────────────────────────────────────────────────────┐
│ L4 End-to-end   correctness · groundedness · completeness ·   │
│                 safety · pass^k                               │
├───────────────────────────────────────────────────────────────┤
│ L3 Trajectory   tool-call failure taxonomy · step efficiency  │
├───────────────────────────────────────────────────────────────┤
│ L2 Generation   faithfulness given gold context (no RAG noise)│
├───────────────────────────────────────────────────────────────┤
│ L1 Retrieval    Recall@K · MRR · nDCG@K                       │
└───────────────────────────────────────────────────────────────┘
```

Each layer is evaluated **in isolation** (e.g. L2 is given gold context) and **in situ** (inside the full pipeline), so errors can be attributed to the right layer.

### 4.2 Evaluation Dimensions

| Dimension | Priority | Method |
|---|---|---|
| Numeric / factual accuracy | Critical | Rule (tolerance-based number matching) |
| Groundedness / citation faithfulness | Critical | Rule (cited chunk exists) + judge (chunk supports claim) |
| Completeness / analytical depth | High | Judge rubric against gold key points |
| Finance-specific safety | Medium | Rule + judge: no fabricated price targets, no personalized advice, abstains when appropriate, resists prompt injection |
| Tone / style | Low | Single judge rubric item |

### 4.3 Judge Panel and Validation (RQ2)

- **Panel:** 3 judges from different model families. Final score is the majority vote or mean.
- **Human anchor:** `~150` outputs hand-labeled by the author.

| Meta-eval | Metric | Result |
|---|---|---|
| Judge vs. human | Cohen's κ (per judge, per dimension) | `x.xx` |
| Judge vs. judge | Fleiss's κ / Krippendorff's α | `x.xx` |
| Position bias | Win-rate shift when answer order is swapped | `x.x%` |
| Verbosity bias | Score vs. length correlation, with quality held fixed | `x.xx` |
| Self-preference | Score difference on outputs from the judge's own family | `x.xx` |
| Judge consistency | Same input, repeated scoring | `x.xx` |

**Takeaway (expected):** which dimensions can safely be judged by an LLM, and which need rules or humans.

## 5. Diagnosing the Agent (RQ1, RQ3)

### 5.1 Retrieval (L1)

| Config | Recall@5 | Recall@10 | MRR | nDCG@10 |
|---|---|---|---|---|
| Dense | `x.xx` | `x.xx` | `x.xx` | `x.xx` |
| Hybrid (BM25 + dense) | `x.xx` | `x.xx` | `x.xx` | `x.xx` |
| Hybrid + rerank | `x.xx` | `x.xx` | `x.xx` | `x.xx` |

### 5.2 Trajectory Failure Taxonomy (L3)

Detected automatically from agent traces:

| Code | Failure mode | Detection |
|---|---|---|
| `T1` | No tool call; answers from parametric memory | Rule |
| `T2` | Calls a tool that doesn't exist | Rule |
| `T3` | Calls the wrong (but valid) tool | Rule vs. expected trajectory |
| `T4` | Malformed or incorrect arguments | Schema + rule |
| `T5` | Tool returns nothing, final answer hallucinates anyway | Rule + judge |
| `T6` | Final answer contradicts or ignores the tool output | Judge |
| `T7` | Redundant loops / exceeds step budget | Rule |
| `T8` | Premature termination | Rule |

**Expected figure:** failure-rate heatmap (models × failure codes).

### 5.3 Error Attribution

For each failed task, we attribute the failure to its root layer: **retrieval miss → tool error → reasoning error**.

**Expected figure:** stacked bar of root-cause share per model.

### 5.4 Reliability (RQ3)

| Model | pass@1 | pass^3 | pass^5 | pass^8 |
|---|---|---|---|---|
| Frontier | `x.xx` | `x.xx` | `x.xx` | `x.xx` |
| Mid | `x.xx` | `x.xx` | `x.xx` | `x.xx` |
| Small (8B) | `x.xx` | `x.xx` | `x.xx` | `x.xx` |

**Expected figure:** pass^k decay curves.

## 6. Knob Ablations (RQ4)

| Knob | Values swept | Δ end-to-end quality | Δ cost | Δ latency |
|---|---|---|---|---|
| Retrieval top-K | 3 / 5 / 10 / 20 | `±x.xx` | `±x%` | `±x%` |
| Chunk size | 256 / 512 / 1024 | `±x.xx` | `±x%` | `±x%` |
| Temperature | 0 / 0.3 / 0.7 | `±x.xx` | — | — |
| Max agent steps | 3 / 5 / 10 | `±x.xx` | `±x%` | `±x%` |
| Reranker | off / on | `±x.xx` | `±x%` | `±x%` |

## 7. Quality vs. Cost/Latency (RQ5)

| Model | Quality | pass^5 | $ / 100 tasks | p50 latency | p95 latency | Tokens / task |
|---|---|---|---|---|---|---|
| Frontier A | `x.xx` | `x.xx` | `$x.xx` | `x.xs` | `x.xs` | `x,xxx` |
| Frontier B | `x.xx` | `x.xx` | `$x.xx` | `x.xs` | `x.xs` | `x,xxx` |
| Mid | `x.xx` | `x.xx` | `$x.xx` | `x.xs` | `x.xs` | `x,xxx` |
| Small (8B, local) | `x.xx` | `x.xx` | `$x.xx` | `x.xs` | `x.xs` | `x,xxx` |
| **Small + post-training** | `x.xx` | `x.xx` | `$x.xx` | `x.xs` | `x.xs` | `x,xxx` |

**Headline figure:** Pareto frontier (quality vs. cost per task), with the post-trained small model as the point that moves.

## 8. Post-Training Small Models (RQ6)

The eval harness doubles as the training signal:

```
ERA-Bench evals ──► filter good trajectories ──► SFT data
                ──► judge-ranked pairs        ──► DPO data
                ──► rule-based checks         ──► GRPO rewards
```

| Stage | Data source | Quality | Tool-error rate | pass^5 | % of frontier |
|---|---|---|---|---|---|
| Baseline (8B) | — | `x.xx` | `xx%` | `x.xx` | `xx%` |
| + SFT | Distilled frontier trajectories that pass the evals | `x.xx` | `xx%` | `x.xx` | `xx%` |
| + DPO | Judge-ranked preference pairs | `x.xx` | `xx%` | `x.xx` | `xx%` |
| + GRPO | Verifiable rewards (valid tool calls, numeric accuracy) | `x.xx` | `xx%` | `x.xx` | `xx%` |

**Additional analyses:**
- Which failure codes (§5.2) each stage fixes
- Overfitting check: held-out companies and held-out task types
- Reward hacking check: rule-based reward goes up, judge score doesn't

## 9. Stretch: Router + Small Models (RQ7)

A small classifier routes each query by difficulty: simple lookups go to the small model, and complex synthesis goes to the frontier model.

| Setup | Quality | $ / 100 tasks | p50 latency |
|---|---|---|---|
| Frontier only | `x.xx` | `$x.xx` | `x.xs` |
| Small only | `x.xx` | `$x.xx` | `x.xs` |
| Router | `x.xx` | `$x.xx` | `x.xs` |

## 10. Limitations

- Human labels come from a single annotator.
- Coverage is limited to US public companies and SEC filings.
- Judge-model families overlap with the models being evaluated, so self-preference is measured but not fully eliminated.
- Cost figures reflect API prices at the time of the experiments.

## 11. Repo Layout (planned)

```
era-eval-and-post-training/
├── bench/          # task definitions, gold answers, gold chunks, splits
├── evals/
│   ├── retrieval/  # L1 metrics
│   ├── generation/ # L2 faithfulness
│   ├── trajectory/ # L3 failure taxonomy
│   ├── e2e/        # L4 rules + judge panel
│   └── meta/       # judge validation (κ, biases)
├── runners/        # model swaps, knob sweeps, pass^k runs
├── posttrain/      # sft/, dpo/, grpo/
├── router/         # stretch
├── reports/        # generated tables and figures
└── README.md
```

## 12. Roadmap

- [ ] **P1** ERA-Bench dataset and gold labels
- [ ] **P2** Eval harness (L1–L4) and judge validation
- [ ] **P3** Baselines: model swaps, knob ablations, Pareto chart
- [ ] **P4** Post-training: SFT → DPO → GRPO
- [ ] **P5** Stretch: router, robustness suite
