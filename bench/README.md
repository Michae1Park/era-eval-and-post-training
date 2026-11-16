# ERA-Bench

One consolidated benchmark for the equity-research-agent. The agent repo keeps its own gold sets; this directory imports them into one schema, records where every task came from, and is where new tasks are added.

```bash
python bench/build.py ../equity-research-agent
```

This regenerates `tasks/*.jsonl`, `manifest.json` (version, agent commit, content hash) and [`COVERAGE.md`](COVERAGE.md).

## Suites

| Suite | Corpus | Modes | Notes |
|---|---|---|---|
| `fy2025` | FY2025 10-Ks of AAPL, AMZN, MSFT, NVDA | `ask_fy2025` | The V1–V3 RAG-agent set. Mostly human-verified; has gold retrieval chunks |
| `marketplaces` | UBER, LYFT, DASH, CART, BKNG, EXPE, ABNB, TRIP, read as of a date | `ask`, `research`, `investigate`, `extraction` | The V4 agent. Drafted by the agent and checked by script, not yet human-reviewed |

## Task schema

| Field | Meaning |
|---|---|
| `id` | Unique, prefixed by mode (`fy25-`, `ask-`, `research-`, `investigate-`, `extract-`) |
| `suite`, `mode` | Which corpus, and which agent entry point runs the task |
| `layers` | Which eval layers the task supports: `retrieval`, `generation`, `trajectory`, `e2e`, `extraction` |
| `category`, `kind` | Task type, from the source gold set |
| `split` | `dev` (fix the agent against it) or `test` (report only) |
| `as_of` | Date the agent reads data as of; `null` for `fy2025` |
| `companies` | Tickers involved |
| `question` | Prompt; `null` for extraction labels |
| `answer` | `type` (`number`, `number_set`, `text`, `abstain`, `model_ref`, `composite`), `values`, `tolerance`, `should_abstain` |
| `required_points` | Points a correct text answer must contain (judge-scored) |
| `expected_gaps` | Caveats a good answer should flag |
| `expected_refs` | Model cell ids a Research answer must cite (regex) |
| `expected_tools` | Tools a correct trajectory should use |
| `evidence` | `gold` and `acceptable` source passages (retrieval and groundedness gold) |
| `parts` | Investigate sub-questions with their own expected answers |
| `requires_assumptions` | Answer depends on model assumptions, which must be stated |
| `failure_mode` | For decline tasks: `unsupported`, `false_premise`, `entity_naming` |
| `review` | `origin`, `verified_by`, `verified_on` |
| `provenance` | Source repo, commit, file and id |

## Rules

- Gold answers come from source documents, never from agent output.
- `test` is not looked at while fixing the agent.
- Every result records `manifest.json`'s `version` and `sha256_16`.
- Imported tasks are changed in the agent repo and re-imported; new tasks are added here.

## Known gaps (to close before freezing v1.0)

| Gap | Why it matters |
|---|---|
| 508 of 578 tasks are not human-verified | Gold errors would read as agent errors |
| No `train` split | Post-training needs task data disjoint from dev/test |
| Only 12 Investigate tasks | Too few for multi-step agent results to be meaningful |
| No retrieval gold for `marketplaces` | Retrieval metrics only cover the `fy2025` suite |
| `expected_tools` is a set, not an ordered trajectory | Limits the tool-use failure checks (T3, T7, T8) |
| No adversarial or prompt-injection tasks | Safety and robustness are untested |
| No multi-turn tasks | The agent supports multi-turn conversations; the benchmark doesn't test them |
| No Report-mode tasks | Note quality is evaluated only inside the agent repo |
