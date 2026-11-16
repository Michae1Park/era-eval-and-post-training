# era-eval-and-post-training

Systematically evaluate, diagnose, and improve AI systems through component-level testing, end-to-end benchmarking, inference optimization, and model post-training.

> **Status: mock draft.** Every number below is a placeholder (`x.xx`). This document sketches the story, the experiments, and the expected artifacts before running anything.

---

## TL;DR

**Eval-driven post-training** for the [equity-research-agent](https://github.com/Michae1Park/equity-research-agent) (ERA), a tool-using RAG agent that answers questions about public companies.

> **Evaluation tells you what's broken. Post-training fixes it. Evaluation proves the fix worked.**

```
 Act 1: MEASURE ──► Act 2: DIAGNOSE ──► Act 3: FIX ──► Act 4: VERIFY
 ERA-Bench +        failure taxonomy    SFT / DPO /     targeted failure
 validated judges   + root-cause        GRPO, each      rates drop, held-out
                    attribution         aimed at a      tests check for
                                        diagnosed       overfitting and
                                        failure         reward gaming
        ▲                                                    │
        └──────────── same eval harness throughout ──────────┘
```

| Headline result (placeholder) | |
|---|---|
| Judge panel agreement with human labels (Cohen's κ) | `x.xx` |
| Top small-model failure modes diagnosed | `T4` bad args (`xx%`), `T5` hallucination after empty tool result (`xx%`) |
| Small model (8B), baseline → post-trained | `x.xx` → `x.xx` (**`xx%` of frontier quality at `x%` of the cost**) |
| Targeted failure rates after post-training | `T4` `xx%` → `x%`, `T5` `xx%` → `x%` |

---

## 1. Motivation

Agent demos look good. Agent *evaluation* rarely holds up to scrutiny:

1. **Single-number scores hide where it fails.** A wrong answer can come from retrieval, tool use, or reasoning, and each one needs a different fix.
2. **LLM judges are used without being validated.** Their agreement with humans, biases, and consistency are rarely reported.
3. **Averages hide unreliability.** An agent that is right 80% of the time but rarely right on *every* attempt cannot be deployed.
4. **Finance is unforgiving.** A single fabricated number makes a report worthless.

This repo treats the ERA as the system under test and evaluates it **layer by layer**, **validates its own judges**, and measures **reliability** as well as accuracy. Then it closes the loop: the diagnosed failures decide **what to post-train**, the eval checks become the **training signal**, and the same harness **verifies** the fix.

## 2. Research Questions

| Act | # | Question | Section |
|---|---|---|---|
| Measure | **RQ1** | Can an LLM-judge panel be trusted for financial research output? | §4 |
| Diagnose | **RQ2** | Where does the agent fail (retrieval, tool use, or generation), and how do failures differ by model size? | §5 |
| Diagnose | **RQ3** | How reliable is the agent across repeated runs (pass^k)? | §5.4 |
| Diagnose | **RQ4** | Which knobs (retrieval K, chunking, temperature, step budget) matter most? | §6 |
| Diagnose | **RQ5** | What is the quality vs. cost/latency Pareto frontier across models? | §7 |
| Fix | **RQ6** | Can post-training aimed at diagnosed failures close the small-to-frontier gap, and which technique fixes which failure? | §8 |
| Verify | **RQ7** | Do the gains hold on held-out data without reward gaming or regressions? | §9 |
| Stretch | **RQ8** | Can a router plus small models match a single large model? | §10 |

## 3. ERA-Bench: The Benchmark

### 3.1 Task Taxonomy

| Category | Example | Ground truth | Checked by |
|---|---|---|---|
| **Factual lookup** | "What was Uber's revenue in Q2 2026?" | Exact value from filing | Rule |
| **Multi-hop / computation** | "What was Lyft's adjusted EBITDA margin on gross bookings in Q2 2026?" | Computed value | Rule |
| **Comparative analysis** | "Which grew room nights faster in Q2 2026, Booking or Expedia, and why?" | Key facts + rubric | Rule + judge |
| **Synthesis / research** | "How does our Q3 2026 forecast for Uber compare with guidance?" | Gold key points + model refs | Judge |
| **Unanswerable / out-of-scope** | "What is your price target for Netflix?" | Should abstain | Rule + judge |
| **Adversarial** | Retrieved doc contains an injected instruction | Should ignore it | Rule |

### 3.2 Dataset Stats

Built by [`bench/`](eval/bench/README.md); current counts in [`bench/COVERAGE.md`](eval/bench/COVERAGE.md).

| Split | # tasks | # companies | Use |
|---|---|---|---|
| dev | 529 | 8 | Fix the agent against it |
| test | 875 (337 are extraction labels) | 8 | Report only |
| train | 1,263 | 6 (TRIP, CART held out) | Post-training only; as-ofs and periods before 2025Q3 |

Test tasks by mode: Ask 260, Research 133, Investigate 76, multi-turn 61, Report 8, plus about 140 adversarial tasks across modes. Multi-step tasks are templated at four as-of dates (one per quarter), so each mode is large enough to report with a CI of roughly ±10 points.

Each task carries its gold answer, gold evidence (chunk ids, XBRL fact ids) where it applies, the expected ordered tool trajectory, and its provenance.

## 4. Act 1: Measurement Methodology

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

### 4.3 Judge Panel and Validation (RQ1)

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

## 5. Act 2: Diagnosing the Agent (RQ2, RQ3)

The output of this act is a **ranked list of failure modes for the small model**, which becomes the target list for Act 3.

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

## 8. Act 3: Fixing It with Post-Training (RQ6)

### 8.1 From Diagnosis to Technique

Each technique is chosen for the failure it is best suited to fix, and its training data comes from the eval harness:

| Diagnosed failure (§5) | Technique | Why this technique | Training signal from evals |
|---|---|---|---|
| `T1`–`T4` tool-call format, wrong tool, bad args | **SFT** | Imitation fixes behavior that follows a learnable pattern | Frontier trajectories that pass all L3 rule checks |
| `T5`–`T6` hallucination, ignoring tool output | **DPO** | Needs a contrast between faithful and unfaithful answers | Judge-ranked pairs: grounded answer vs. unsupported one |
| Numeric errors, `T7`–`T8` inefficient trajectories | **GRPO** | Correctness can be checked exactly, so reward it directly | Rule-based rewards: number matches gold, valid calls, step penalty |

### 8.2 Setup

Single L40S (48 GB).

| Technique | Model | Method |
|---|---|---|
| SFT, DPO | 7–8B | LoRA |
| GRPO | 3–4B (7–8B if it scales) | LoRA, vLLM rollouts on the same GPU |

### 8.3 Results

| Stage | Quality | `T1–T4` rate | `T5–T6` rate | Numeric acc. | pass^5 | % of frontier |
|---|---|---|---|---|---|---|
| Baseline | `x.xx` | `xx%` | `xx%` | `xx%` | `x.xx` | `xx%` |
| + SFT | `x.xx` | **`x%`** | `xx%` | `xx%` | `x.xx` | `xx%` |
| + DPO | `x.xx` | `x%` | **`x%`** | `xx%` | `x.xx` | `xx%` |
| + GRPO | `x.xx` | `x%` | `x%` | **`xx%`** | `x.xx` | `xx%` |

**Expected figure:** failure-code heatmap before vs. after each stage, showing that each technique moves its target column.

## 9. Act 4: Verifying the Fix (RQ7)

The same harness checks that the gains are real:

| Check | Method | Result |
|---|---|---|
| Generalization | Held-out companies and held-out task types | `x.xx` vs. `x.xx` in-distribution |
| Reward gaming | GRPO rule reward rises but judge score doesn't | `x.xx` correlation |
| Regressions | Untargeted dimensions (safety, abstention, tone) don't drop | `±x.xx` |
| Judge circularity | DPO-trained model scored by a judge outside the training panel | `x.xx` vs. `x.xx` |
| Reliability | pass^k curve of post-trained vs. baseline | `x.xx` → `x.xx` |
| Cost position | Post-trained model's new point on the §7 Pareto chart | `$x.xx`, `x.xx` quality |

## 10. Stretch: Router + Small Models (RQ8)

A small classifier routes each query by difficulty: simple lookups go to the small model, and complex synthesis goes to the frontier model.

| Setup | Quality | $ / 100 tasks | p50 latency |
|---|---|---|---|
| Frontier only | `x.xx` | `$x.xx` | `x.xs` |
| Small only | `x.xx` | `$x.xx` | `x.xs` |
| Router | `x.xx` | `$x.xx` | `x.xs` |

## 11. Limitations

- Human labels come from a single annotator.
- Coverage is limited to US public companies and SEC filings.
- Judge-model families overlap with the models being evaluated, so self-preference is measured but not fully eliminated.
- Cost figures reflect API prices at the time of the experiments.

## 12. Running the Eval

```bash
uv sync                                                    # installs the agent as an editable path dependency
uv run python eval/bench/src/build.py ../equity-research-agent  # ERA-Bench
uv run python eval/harness/run.py --label v1-<commit> --split dev --k 4
uv run python eval/scoring/score.py results/v1-<commit>/dev
uv run python eval/scoring/compare.py results/v1-<commit>/dev results/v2-<commit>/dev
```

`eval/harness/` evaluates any agent behind the `AgentUnderTest` interface (`eval/harness/agents/`; the ERA agent is `agents/era.py`). `eval/harness/config.yaml` pins model, budgets, search, timeouts and retries. Each task runs under a deadline checked at every model and tool call; transient server errors are retried with backoff; failures are classed as `agent_error`, `timeout` (counted against the agent) or `harness_error`, `infra_error` (rerun on resume, never scored); SIGINT/SIGTERM stop cleanly and keep written traces. Every run is logged in `results/runs.jsonl`. The harness writes one JSON trace per run: every model turn and tool call with arguments, results, tokens and timing, stamped with the agent commit and bench hash. Injection tasks wrap the agent's tools to plant the payload. `eval/scoring/` applies rule checks (numbers within tolerance, model-cell refs, abstention, canaries, faithfulness of cited numbers, required tools, ordered calls with key arguments, forbidden tools, repeats, tool errors, budget) and reports pass@1 with 95% CIs (Wilson via statsmodels for k = 1, task-level bootstrap via scipy for k > 1) and pass^k by mode, category and held-out company. `compare.py` pairs two runs task by task: delta with a bootstrap CI, McNemar's exact test, and the lists of fixed and broken tasks. Judge-scored points are flagged for the judge pass.

## 13. Repo Layout

```
era-eval-and-post-training/
├── eval/
│   ├── bench/      # ERA-Bench tasks, gold answers, splits, builder
│   ├── harness/    # runner, AgentUnderTest interface, injection, runtime
│   └── scoring/    # rule checks, statistics, paired run comparison (+ judge)
├── training/       # trajectory export and filtering, SFT → DPO → GRPO
├── results/        # run traces, scores, comparisons; shared by eval and training
└── README.md
```

`training/` imports from `eval/`, never the reverse, so the benchmark stays independent of training code.

## 14. Roadmap

- [ ] **P1 Measure:** ERA-Bench dataset, gold labels, eval harness (L1–L4), judge validation
- [ ] **P2 Diagnose:** model swaps, failure taxonomy, pass^k, knob ablations, Pareto chart
- [ ] **P3 Fix:** SFT → DPO → GRPO, each aimed at its diagnosed failures
- [ ] **P4 Verify:** held-out, reward-gaming, regression, and judge-circularity checks
- [ ] **P5 Stretch:** router, robustness suite
