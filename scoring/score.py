import argparse
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "bench" / "tasks"


def wilson(passed: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (0.0, 0.0)
    p = passed / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(centre - half, 3), round(centre + half, 3))


def aggregate(rows: list[dict], key) -> dict:
    groups = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["pass"] is not None:
            groups[key(row)][row["task_id"]].append(row["pass"])
    out = {}
    for group, tasks in sorted(groups.items()):
        n = len(tasks)
        pass1 = sum(sum(s) / len(s) for s in tasks.values()) / n
        pass_k = sum(all(s) for s in tasks.values())
        k = min(len(s) for s in tasks.values())
        out[group] = {"tasks": n, "k": k, "pass@1": round(pass1, 3),
                      "ci95": wilson(round(pass1 * n), n), f"pass^{k}": round(pass_k / n, 3)}
    return out


def rate(rows: list[dict], field: str) -> dict:
    counts = defaultdict(lambda: [0, 0])
    for row in rows:
        for name, value in row[field].items():
            if isinstance(value, bool):
                counts[name][0] += value
                counts[name][1] += 1
    return {k: {"rate": round(a / b, 3), "n": b} for k, (a, b) in sorted(counts.items())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", help="results/<label>/<split>")
    args = ap.parse_args()
    run = Path(args.run).resolve()
    info = json.loads((run / "run.json").read_text())
    repo = (ROOT / info["config"]["agent_repo"]).resolve()
    os.environ.setdefault("ERA_COMPANIES", str(repo / info["config"]["companies"]))
    os.chdir(repo)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from rules import score

    tasks = {}
    for split in ("dev", "test", "train"):
        for line in (TASKS / f"{split}.jsonl").open():
            task = json.loads(line)
            tasks[task["id"]] = task
    rows = []
    for line in (run / "traces.jsonl").open():
        record = json.loads(line)
        task = tasks[record["task_id"]]
        rows.append({"task_id": task["id"], "sample": record["sample"], "mode": task["mode"],
                     "category": task["category"], "status": record["status"],
                     "stop": record.get("stop"), "seconds": record["seconds"],
                     "tokens": record.get("tokens"), "tags": task.get("tags") or []}
                    | score(task, record))
    with (run / "scores.jsonl").open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    summary = {
        "run": info | {"config": None},
        "overall": aggregate(rows, lambda r: "all"),
        "by_mode": aggregate(rows, lambda r: r["mode"]),
        "by_category": aggregate(rows, lambda r: f"{r['mode']}/{r['category']}"),
        "holdout_companies": aggregate(rows, lambda r: "holdout" if "holdout_company" in r["tags"] else "seen"),
        "outcome_checks": rate(rows, "outcome"),
        "trajectory_checks": rate(rows, "trajectory"),
        "errors": sum(r["status"] != "ok" for r in rows),
        "judge_pending": sum(r["judge_needed"] for r in rows),
        "seconds_mean": round(sum(r["seconds"] for r in rows) / max(len(rows), 1), 1),
        "tokens_mean": {k: round(sum((r["tokens"] or {}).get(k, 0) for r in rows) / max(len(rows), 1))
                        for k in ("input", "output")},
    }
    (run / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("overall", "by_mode", "outcome_checks", "trajectory_checks", "errors")}, indent=1))


if __name__ == "__main__":
    main()
