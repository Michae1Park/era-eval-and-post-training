import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "eval" / "bench" / "tasks"
NAMES = {"T1": "no tool call, parametric answer", "T2": "nonexistent tool", "T3": "wrong valid tool",
         "T4": "malformed or incorrect args", "T5": "empty tool result, hallucinates anyway",
         "T6": "contradicts or ignores tool output", "T7": "loops or exceeds step budget",
         "T8": "premature termination", "T0": "unclassified reasoning error"}
BUDGET_ERRORS = ("Tool budget used up", "You already made this exact call")
REFUSALS = ("refusal", "refusal_with_info", "abstain")


def tool_calls(record: dict) -> list[dict]:
    return [s for s in record.get("steps") or [] if s.get("kind") == "tool"]


def error_of(call: dict) -> str | None:
    result = call.get("result")
    return result.get("error") if isinstance(result, dict) and isinstance(result.get("error"), str) else None


def empty(call: dict) -> bool:
    result = call.get("result")
    if error_of(call):
        return True
    if isinstance(result, dict) and "_cut" not in result:
        payload = {k: v for k, v in result.items() if k not in ("company", "ticker", "query")}
        return not any(v not in (None, [], {}, "") for v in payload.values())
    return result in (None, [], {}, "")


def claims(answer) -> list[dict]:
    return [c for c in (answer or {}).get("claims") or [] if isinstance(c, dict)] if isinstance(answer, dict) else []


def retrieval_miss(task: dict, calls: list[dict]) -> bool | None:
    wanted = set(task["evidence"].get("chunk_ids") or []) | {i for p in task.get("parts") or [] for i in p.get("chunk_ids") or []}
    wanted |= set(task["evidence"].get("fact_ids") or [])
    if not wanted:
        return None
    seen = " ".join(json.dumps(c.get("result"), default=str) for c in calls)
    return not any(w in seen for w in wanted)


def codes(task: dict, record: dict, score: dict) -> list[str]:
    calls = tool_calls(record)
    names = [c["name"] for c in calls]
    errors = [e for e in map(error_of, calls) if e]
    spec = task.get("trajectory") or {}
    expected = spec.get("expected_tools") or [o["tool"] for o in spec.get("ordered") or []]
    traj, outcome, judge = score.get("trajectory") or {}, score.get("outcome") or {}, score.get("judge") or {}
    answer = record.get("answer")
    abstained = isinstance(answer, dict) and bool(answer.get("abstained"))
    refusal = task["answer"].get("type") in REFUSALS
    found = []
    if any(e.startswith("unknown tool") for e in errors):
        found.append("T2")
    if record.get("stop") == "budget" or traj.get("no_repeats") is False or any(e.startswith(BUDGET_ERRORS) for e in errors):
        found.append("T7")
    if not calls and not refusal and not abstained:
        found.append("T1")
    if any(e.startswith(("bad arguments", "unknown metric", "unknown lines", "unknown drivers", "name the companies",
                         "give ", "series:")) for e in errors) or traj.get("ordered_args") is False and not set(expected) - set(names):
        found.append("T4")
    if calls and expected and set(expected) - set(names):
        found.append("T8" if len(calls) < len(expected) and record.get("stop") in ("answered", "done") else "T3")
    if calls and all(empty(c) for c in calls) and not abstained and not refusal:
        found.append("T5")
    if judge.get("grounded") is False or outcome.get("faithful") is False:
        found.append("T6")
    return found or ["T0"]


def root_layer(task: dict, record: dict, found: list[str]) -> str:
    if retrieval_miss(task, tool_calls(record)):
        return "retrieval"
    if set(found) & {"T1", "T2", "T3", "T4", "T7", "T8"}:
        return "tool"
    return "reasoning"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", help="results/<label>/<split> after score.py (and judge.py)")
    args = ap.parse_args()
    run = Path(args.run).resolve()
    tasks = {json.loads(l)["id"]: json.loads(l) for s in ("dev", "test", "train") for l in (TASKS / f"{s}.jsonl").open()}
    traces = {}
    for line in (run / "traces.jsonl").open():
        r = json.loads(line)
        traces[(r["task_id"], r["sample"])] = r
    rows = []
    for line in (run / "scores.jsonl").open():
        s = json.loads(line)
        if s["pass"] is not False or s["status"] != "ok":
            continue
        task, record = tasks[s["task_id"]], traces[(s["task_id"], s["sample"])]
        found = codes(task, record, s)
        rows.append({"task_id": s["task_id"], "sample": s["sample"], "mode": s["mode"], "category": s["category"],
                     "codes": found, "primary": found[0], "root": root_layer(task, record, found)})
    with (run / "failures.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    scored = sum(1 for l in (run / "scores.jsonl").open() if json.loads(l)["pass"] is not None)
    any_code = Counter(c for r in rows for c in r["codes"])
    by_mode = defaultdict(Counter)
    for r in rows:
        by_mode[r["mode"]].update(r["codes"])
    summary = {"scored": scored, "failed": len(rows),
               "codes": {c: {"name": NAMES[c], "failures": n, "rate_of_scored": round(n / max(scored, 1), 3)}
                         for c, n in any_code.most_common()},
               "primary": dict(Counter(r["primary"] for r in rows).most_common()),
               "root_layer": dict(Counter(r["root"] for r in rows).most_common()),
               "by_mode": {m: dict(c.most_common()) for m, c in sorted(by_mode.items())}}
    (run / "taxonomy.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
