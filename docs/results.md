# Results

Placeholders (`x.xx`) unless noted. Methods are in [`plan.md`](plan.md), in the same order. Test split unless noted.

## 0. Headline

| | |
|---|---|
| Retrieval hit@8 (dev) | 0.69 |
| Judge vs. human (Cohen's κ) | `x.xx` |
| Top small-model failures | T4 `xx%`, T5 `xx%` |
| Small (8B): baseline → post-trained | `x.xx` → `x.xx` (`xx%` of 27B) |
| Targeted failure rates | T4 `xx%` → `x%`, T5 `xx%` → `x%` |

## 1. Retrieval (M1, M1.1)

Real numbers. Dev, 163 queries; Qwen3-Embedding-0.6B + bge-reranker-v2-m3, hybrid with rewrite and fan-out, K=8. Full output in `results/retrieval-baseline/dev/`.

| Mode | hit@1 | hit@5 | hit@8 | recall@8 | MRR | nDCG@8 |
|---|---|---|---|---|---|---|
| All | 0.25 | 0.59 | 0.69 | 0.54 | 0.38 | 0.39 |
| Ask | 0.27 | 0.55 | 0.66 | 0.56 | 0.37 | 0.40 |
| Investigate | 0.19 | 0.73 | 0.78 | 0.47 | 0.39 | 0.35 |

## 2. Generation (M2, M2.1–M2.2)

| Model | Faithfulness, gold context | Faithfulness, full pipeline |
|---|---|---|
| Qwen3.6-27B | `x.xx` | `x.xx` |
| Qwen3.5-9B | `x.xx` | `x.xx` |
| Qwen3-1.7B | `x.xx` | `x.xx` |

## 3. Tool use (M3, M3.1)

| Model | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 |
|---|---|---|---|---|---|---|---|---|
| Qwen3.6-27B | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` |
| Qwen3.5-9B | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` |
| Qwen3-1.7B | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` | `x%` |

## 4. Judges (M4, M4.1–M4.5)

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

## 5. End to end (M5, M5.1–M5.2)

| Model | Quality | pass@1 | pass^3 | pass^5 | pass^8 |
|---|---|---|---|---|---|
| Qwen3.6-27B | `x.xx` | `x.xx` | `x.xx` | `x.xx` | `x.xx` |
| Qwen3.5-9B | `x.xx` | `x.xx` | `x.xx` | `x.xx` | `x.xx` |

## 6. Forecast accuracy (M6, M6.1–M6.2)

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

## 7. Root cause and model size (D1, D1.1–D1.2)

| Model | Retrieval | Tool | Reasoning | Quality | pass^4 | p50 | Tokens/task |
|---|---|---|---|---|---|---|---|
| Qwen3.6-27B | `xx%` | `xx%` | `xx%` | `x.xx` | `x.xx` | `x.xs` | `x,xxx` |
| Gemma-4-31B | `xx%` | `xx%` | `xx%` | `x.xx` | `x.xx` | `x.xs` | `x,xxx` |
| Qwen3.5-9B | `xx%` | `xx%` | `xx%` | `x.xx` | `x.xx` | `x.xs` | `x,xxx` |
| Qwen3-1.7B | `xx%` | `xx%` | `xx%` | `x.xx` | — | `x.xs` | `x,xxx` |

## 8. Knobs (D2, D2.1–D2.4)

| Knob | Values | Δ quality | Δ latency |
|---|---|---|---|
| Top-K | 4/8/16 | `±x.xx` | `±x%` |
| Reranker | off/on | `±x.xx` | `±x%` |
| Max tool calls | 8/20 | `±x.xx` | `±x%` |
| Temperature | 0/0.7 | `±x.xx` | — |

## 9. Post-training (F1, F1.1–F1.4)

| Stage | Quality | T1–T4 | T5–T6 | Numeric acc. | T7–T8 | pass^5 | % of 27B |
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

## 10. Verification (V1, V1.1–V1.7)

| Check | Baseline | Post-trained |
|---|---|---|
| In-distribution quality | `x.xx` | `x.xx` |
| Held-out companies (TRIP, CART) | `x.xx` | `x.xx` |
| Held-out task types | `x.xx` | `x.xx` |
| Safety / abstention | `x.xx` | `x.xx` |
| Injection resistance | `x.xx` | `x.xx` |
| Tone | `x.xx` | `x.xx` |
| pass^5 | `x.xx` | `x.xx` |
| Score from an outside judge | `x.xx` | `x.xx` |
| Forecast EPS MdAPE | `x.x%` | `x.x%` |

| Reward-gaming check | Result |
|---|---|
| GRPO rule reward vs. judge score correlation | `x.xx` |

## 11. Router (S1, S1.1, stretch)

| Setup | Quality | p50 |
|---|---|---|
| 27B only | `x.xx` | `x.xs` |
| Small only | `x.xx` | `x.xs` |
| Router | `x.xx` | `x.xs` |
