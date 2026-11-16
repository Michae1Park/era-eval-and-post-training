# ERA-Bench

One consolidated benchmark for the equity-research-agent's V4 scope: eight online marketplaces (UBER, LYFT, DASH, CART, BKNG, EXPE, ABNB, TRIP), every task read as of a date. The FY2025 Big Tech sets stay in the agent repo as legacy and are not imported.

```bash
python eval/bench/src/build.py ../equity-research-agent   # tasks/{dev,test,train}.jsonl, manifest.json, COVERAGE.md
python bench/src/render.py                           # review/era-bench-review.pdf
```

See [`COVERAGE.md`](COVERAGE.md) for current counts.

## Where tasks come from

| Source | Code | Gold from | Tasks |
|---|---|---|---|
| Agent gold sets (Ask, Research, Investigate, Extraction) | `src/imported.py` | Agent repo `evaluation/gold/` | ~500 |
| Templated from SEC XBRL | `src/generate.py` | `facts` table (SEC companyfacts / inline XBRL), never agent output | lookups, y/y growth, margins, derived Q4, peer comparisons, trends |
| Templated from extraction labels | `src/generate.py` | 337 cross-checked KPI labels with release quotes | KPI lookups, guidance ranges, guide vs actual, EBITDA margins, injection variants |
| Templated from filing dates | `src/generate.py` | EDGAR release dates | As-of traps (asked two days before the release) |
| Templated multi-step | `src/multistep.py` | KPI labels, guidance, XBRL revenue (Q4 = FY − 9M), and model cell-id patterns at four eval as-ofs (one per quarter, 2025Q3–2026Q2) | Research (forecast, scenario, valuation, variance, peers), Investigate (guide beat, growth + scenario, margin path, peer growth vs value), multi-turn chains, adversarial (tool lures, units, false premises, conduct refusals, injections into model and search tools) |
| Hand-drafted | `drafted/*.yaml` → `src/drafted.py` | Filing passages (chunk ids) and `kpi:`/`guide:`/`xbrl:` refs resolved at build | Investigate, adversarial, multi-turn, filing text, Report |

Drafted values are written as references (`kpi:UBER:gross_bookings:mobility:2026Q2`) or formulas (`growth`, `ratio`, `per_unit`) and resolved from source data at build time. A reference that doesn't resolve, or a chunk id that doesn't exist, fails the build.

## Splits

| Split | Rule |
|---|---|
| `dev` | Fix the agent against it |
| `test` | Report only; don't look while fixing |
| `train` | Post-training only. Periods before 2025Q3 (disjoint from dev/test, which are 2025Q3 onwards), and no TRIP or CART tasks, so those two are held-out companies (tagged `holdout_company` in dev/test) |

Generated eval tasks are capped at 24 per (category, kind) (40 for multi-step), spread round-robin across companies. Multi-step train tasks use as-ofs in 2024Q1–2025Q1; their model-ref patterns and XBRL values are checkable, so they serve as verifiable prompts. `prompt_only` train tasks have no gold answer; they are prompts for distillation (SFT) and preference data (DPO). XBRL train tasks have gold values, usable as verifiable rewards (GRPO).

## Task schema

| Field | Meaning |
|---|---|
| `id`, `mode`, `category`, `kind`, `tags` | What the task is. Modes: `ask`, `research`, `investigate`, `multi_turn`, `report`, `extraction` |
| `layers` | Eval layers it supports: `retrieval`, `generation`, `trajectory`, `e2e`, `safety`, `multi_turn`, `report`, `extraction` |
| `split`, `as_of`, `companies` | Split, as-of date, tickers |
| `question` / `turns` | Single prompt, or a conversation with per-turn gold (`resolves_to` states what an elliptical follow-up means) |
| `answer` | `type`, `values`, `tolerance`, `should_abstain` |
| `required_points`, `expected_gaps` | Judge-scored content and caveats |
| `expected_refs`, `parts` | Model cell ids (Research) and sub-questions (Investigate) |
| `trajectory` | `expected_tools`, `ordered` steps with key arguments and periods, `forbidden_tools` |
| `evidence` | Gold quotes, matched `chunk_ids` / `parent_chunk_ids` (retrieval gold), XBRL `fact_ids` |
| `injection` | Prompt-injection payload, the tool it is inserted into, and a `canary` string whose presence in the answer is a failure |
| `report` | Note checks and the figures it must include |
| `failure_mode` | For declines: `unsupported`, `false_premise`, `entity_naming`, `not_yet_reported` |
| `review` | `origin`, `verified_by`, `verified_on` |
| `provenance` | Source file, id or generator, agent commit |

## Review

`src/render.py` writes a review PDF with every dev/test task and a sample of train. Add reviewed ids to `review/verified.tsv` (`id<TAB>reviewer<TAB>date`) and rebuild; those tasks are marked verified.

## Rules

- Gold comes from source data (XBRL, release quotes, filing passages), never from agent output.
- `test` is not looked at while fixing the agent.
- Every result records the manifest's `version` and `sha256_16`.
- Imported tasks are changed in the agent repo and re-imported; new tasks go in `src/generate.py` or `drafted/`.
