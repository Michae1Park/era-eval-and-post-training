# Results

All numbers are placeholders. Methods are in [`plan.md`](plan.md). Test split unless noted.

## 0. Headline

| | |
|---|---|
| Judge vs. human (Cohen's κ) | `x.xx` |
| Top small-model failures | T4 `xx%`, T5 `xx%` |
| Small (8B): baseline → post-trained | `x.xx` → `x.xx` (`xx%` of frontier at `x%` of cost) |
| Targeted failure rates | T4 `xx%` → `x%`, T5 `xx%` → `x%` |

## 1. Judges are trustworthy (RQ1)

| Meta-eval | Metric | Result |
|---|---|---|
| Judge vs. human | Cohen's κ | `x.xx` |
| Judge vs. judge | Krippendorff's α | `x.xx` |
| Position bias | Win-rate shift on swap | `x.x%` |
| Verbosity bias | Length correlation, quality fixed | `x.xx` |
| Self-preference | Own-family score Δ | `x.xx` |
| Consistency | Repeat-scoring agreement | `x.xx` |

| Dimension | κ vs. human | Scored by |
|---|---|---|
| Numeric accuracy | `x.xx` | Rule |
| Groundedness | `x.xx` | Rule + judge |
| Completeness | `x.xx` | Judge |
| Safety | `x.xx` | Rule + judge |
| Tone | `x.xx` | Judge |

## 2. Where it fails (RQ2)

**Retrieval (L1)**

| Config | Recall@5 | Recall@10 | MRR | nDCG@10 |
|---|---|---|---|---|
| Dense | `x.xx` | `x.xx` | `x.xx` | `x.xx` |
| Hybrid | `x.xx` | `x.xx` | `x.xx` | `x.xx` |
| Hybrid + rerank | `x.xx` | `x.xx` | `x.xx` | `x.xx` |

**Generation in isolation vs. in situ (L2)**

| Model | Faithfulness, gold context | Faithfulness, full pipeline |
|---|---|---|
| Frontier | `x.xx` | `x.xx` |
| Mid | `x.xx` | `x.xx` |
| Small (8B) | `x.xx` | `x.xx` |

**Trajectory failure rates (L3)**

| Model | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 |
|---|---|---|---|---|---|---|---|---|
| Frontier | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` |
| Mid | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` |
| Small (8B) | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` |

**Root-cause share of failed tasks**

| Model | Retrieval | Tool | Reasoning |
|---|---|---|---|
| Frontier | `xx%` | `xx%` | `xx%` |
| Mid | `xx%` | `xx%` | `xx%` |
| Small (8B) | `xx%` | `xx%` | `xx%` |

## 3. Reliability (RQ3)

| Model | pass@1 | pass^3 | pass^5 | pass^8 |
|---|---|---|---|---|
| Frontier | `x.xx` | `x.xx` | `x.xx` | `x.xx` |
| Mid | `x.xx` | `x.xx` | `x.xx` | `x.xx` |
| Small (8B) | `x.xx` | `x.xx` | `x.xx` | `x.xx` |

## 4. Knobs (RQ4)

| Knob | Values | Δ quality | Δ cost | Δ latency |
|---|---|---|---|---|
| Top-K | 3/5/10/20 | `±x.xx` | `±x%` | `±x%` |
| Chunk size | 256/512/1024 | `±x.xx` | `±x%` | `±x%` |
| Temperature | 0/0.3/0.7 | `±x.xx` | — | — |
| Max steps | 3/5/10 | `±x.xx` | `±x%` | `±x%` |
| Reranker | off/on | `±x.xx` | `±x%` | `±x%` |

## 5. Cost frontier (RQ5)

| Model | Quality | pass^5 | $/100 tasks | p50 | p95 | Tokens/task |
|---|---|---|---|---|---|---|
| Frontier A | `x.xx` | `x.xx` | `$x.xx` | `x.xs` | `x.xs` | `x,xxx` |
| Frontier B | `x.xx` | `x.xx` | `$x.xx` | `x.xs` | `x.xs` | `x,xxx` |
| Mid | `x.xx` | `x.xx` | `$x.xx` | `x.xs` | `x.xs` | `x,xxx` |
| Small (8B) | `x.xx` | `x.xx` | `$x.xx` | `x.xs` | `x.xs` | `x,xxx` |

## 6. Post-training fixes its targets (RQ6)

| Stage | Quality | T1–T4 | T5–T6 | Numeric acc. | T7–T8 | pass^5 | % of frontier |
|---|---|---|---|---|---|---|---|
| Baseline | `x.xx` | `xx%` | `xx%` | `xx%` | `xx%` | `x.xx` | `xx%` |
| + SFT | `x.xx` | **`x%`** | `xx%` | `xx%` | `xx%` | `x.xx` | `xx%` |
| + DPO | `x.xx` | `x%` | **`x%`** | `xx%` | `xx%` | `x.xx` | `xx%` |
| + GRPO | `x.xx` | `x%` | `x%` | **`xx%`** | **`x%`** | `x.xx` | `xx%` |

| Comparison | Δ quality [95% CI] | McNemar p | Fixed / broken |
|---|---|---|---|
| Baseline → SFT | `+x.xx [x, x]` | `x.xxx` | `xx / xx` |
| SFT → DPO | `+x.xx [x, x]` | `x.xxx` | `xx / xx` |
| DPO → GRPO | `+x.xx [x, x]` | `x.xxx` | `xx / xx` |

## 7. The fix is real (RQ7)

| Check | Baseline | Post-trained |
|---|---|---|
| In-distribution quality | `x.xx` | `x.xx` |
| Held-out companies (TRIP, CART) | `x.xx` | `x.xx` |
| Held-out task types | `x.xx` | `x.xx` |
| Safety / abstention | `x.xx` | `x.xx` |
| Injection resistance | `x.xx` | `x.xx` |
| Tone | `x.xx` | `x.xx` |
| Score from an outside judge | `x.xx` | `x.xx` |
| pass^5 | `x.xx` | `x.xx` |

| Reward-gaming check | Result |
|---|---|
| GRPO rule reward vs. judge score correlation | `x.xx` |

## 8. Updated cost frontier (RQ5 + RQ6)

| Model | Quality | pass^5 | $/100 tasks | p50 |
|---|---|---|---|---|
| Frontier A | `x.xx` | `x.xx` | `$x.xx` | `x.xs` |
| Small (8B) | `x.xx` | `x.xx` | `$x.xx` | `x.xs` |
| **Small + post-training** | `x.xx` | `x.xx` | `$x.xx` | `x.xs` |

## 9. Router (RQ8, stretch)

| Setup | Quality | $/100 tasks | p50 |
|---|---|---|---|
| Frontier only | `x.xx` | `$x.xx` | `x.xs` |
| Small only | `x.xx` | `$x.xx` | `x.xs` |
| Router | `x.xx` | `$x.xx` | `x.xs` |

## 10. Forecast accuracy (L5)

Real numbers. `defaults` proposer (no LLM), 8 companies, releases 2024Q4 to 2026Q1, next-quarter forecasts. Full table in `results/forecast/defaults/report.md`.

| Metric | Forecasts | Agent MdAPE | Naive MdAPE | Agent beats naive (95% CI) | Wilcoxon p |
|---|---|---|---|---|---|
| Revenue | 48 | 2.6% | 2.9% | 23/48 (35–62%) | 0.18 |
| Main KPI | 42 | 1.3% | 1.2% | 17/42 (27–56%) | 0.86 |
| Diluted EPS | 47 | 45.9% | 77.9% | 34/43 (65–89%) | <0.001 |

**EPS vs. consensus** (23 of 47 quarters on a matching basis):

| | Result |
|---|---|
| Agent closer than consensus | 10/23 (43%, 95% CI 26–63%) |
| MdAPE agent vs. consensus | 24.3% vs. 22.2% (Wilcoxon p 0.71) |
| Both missed by >10% | 13 (genuine surprises, e.g. UBER equity revaluations) |
| Agent missed, Street close | 5 (ABNB 25Q1–Q2, CART 25Q2, BKNG 26Q2, EXPE 25Q3) |
| Agent close, Street missed | 3 (CART 25Q3, 26Q2; DASH 26Q1) |

**Read:** revenue and KPI forecasts are no better than seasonal naive. EPS beats naive clearly and is statistically indistinguishable from consensus, but n is small. The five agent-only misses are the ones to investigate.
