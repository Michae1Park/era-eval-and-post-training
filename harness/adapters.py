import json
import time
from dataclasses import asdict
from pathlib import Path

from inject import wrap as wrap_injection


def _cut(value, limit: int):
    text = json.dumps(value, ensure_ascii=False, default=str)
    return value if len(text) <= limit else {"_cut": text[:limit]}


def _steps(run, limit: int, scope: str = "main") -> list[dict]:
    steps = []
    for step in run.steps:
        row = asdict(step) | {"scope": scope}
        row["result"] = _cut(row["result"], limit) if row["result"] is not None else None
        steps.append(row)
    return steps


def _agent(factory, task: dict, tool_set: str, injected: list, session=None):
    agent = factory(task["as_of"], tool_set, session)
    if task.get("injection"):
        wrap_injection(agent.toolbox, task["injection"], injected)
    return agent


def run_single(ctx, task: dict) -> dict:
    injected: list = []
    agent = _agent(ctx.factory, task, task["mode"], injected)
    run = agent.run(task["question"])
    return {"answer": run.answer, "stop": run.stop, "reply": run.reply,
            "steps": _steps(run, ctx.result_chars), "injected": injected}


def run_multi_turn(ctx, task: dict) -> dict:
    from era_agent.agent.history import answer_text, as_messages

    history, turns, injected = [], [], []
    for turn in task["turns"]:
        tool_set = "research" if turn.get("expected_refs") else "ask"
        agent = _agent(ctx.factory, task, tool_set, injected)
        run = agent.run(turn["question"], as_messages(history))
        turns.append({"turn": turn["turn"], "tool_set": tool_set, "question": turn["question"],
                      "answer": run.answer, "stop": run.stop,
                      "steps": _steps(run, ctx.result_chars, f"turn-{turn['turn']}")})
        history.append({"question": turn["question"], "answer": answer_text(run.answer)})
    return {"turns": turns, "stop": turns[-1]["stop"], "answer": turns[-1]["answer"],
            "steps": [s for t in turns for s in t["steps"]], "injected": injected}


def run_investigate(ctx, task: dict) -> dict:
    from era_agent.agent.plan import Investigator

    injected: list = []
    research = _agent(ctx.factory, task, "research", injected)
    ask = _agent(ctx.factory, task, "ask", injected, research.toolbox.book)
    inv = Investigator(research.model, {"ask": ask, "research": research}).run(task["question"])
    data = json.loads(json.dumps(inv.to_dict(), default=str))
    steps = [s | {"scope": "planner"} for s in data.pop("steps")]
    for sub in data["sub_runs"]:
        for step in sub.pop("steps"):
            step["result"] = _cut(step.get("result"), ctx.result_chars)
            steps.append(step | {"scope": f"{sub['id']}:{sub['mode']}"})
    return {"answer": inv.answer, "stop": inv.stop, "investigation": data, "steps": steps,
            "injected": injected}


def run_report(ctx, task: dict) -> dict:
    from era_agent.research import pipeline
    from era_agent.research.forecast import knobs

    out = ctx.out / "reports"
    result = pipeline.run(ctx.db, task["companies"][0], task["as_of"], knobs(), True, False,
                          ctx.report_search(), out)
    return {"answer": None, "stop": "done", "report": _cut(result, 20000),
            "report_dir": str(out / task["companies"][0] / task["as_of"]), "steps": []}


ADAPTERS = {"ask": run_single, "research": run_single, "multi_turn": run_multi_turn,
            "investigate": run_investigate, "report": run_report}


def execute(ctx, task: dict, sample: int) -> dict:
    started = time.perf_counter()
    record = {"task_id": task["id"], "sample": sample, "mode": task["mode"],
              "as_of": task["as_of"], "split": task["split"]}
    try:
        record |= ADAPTERS[task["mode"]](ctx, task) | {"status": "ok"}
    except Exception as e:  # noqa: BLE001
        record |= {"status": "error", "error": f"{type(e).__name__}: {e}"[:2000]}
    record["seconds"] = round(time.perf_counter() - started, 2)
    steps = record.get("steps") or []
    record["tokens"] = {"input": sum(s.get("input_tokens") or 0 for s in steps),
                        "output": sum(s.get("output_tokens") or 0 for s in steps)}
    return record
