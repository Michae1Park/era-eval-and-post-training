import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import bootstrap
from statsmodels.stats.proportion import proportion_confint

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "bench" / "tasks"
NOT_SCORED = ("harness_error", "infra_error")


def ci95(task_means: list[float], k: int) -> tuple[float, float]:
    n = len(task_means)
    if k == 1 or n < 2 or len(set(task_means)) == 1:
        low, high = proportion_confint(round(sum(task_means)), n, method="wilson")
    else:
        result = bootstrap((np.array(task_means),), np.mean, n_resamples=5000, method="percentile", random_state=0)
        low, high = result.confidence_interval
    return (round(float(low), 3), round(float(high), 3))


def latest(path: Path) -> list[dict]:
    records = {}
    for line in path.open():
        record = json.loads(line)
        records[(record["task_id"], record["sample"])] = record
    return list(records.values())


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
                      "ci95": ci95([sum(s) / len(s) for s in tasks.values()], k), f"pass^{k}": round(pass_k / n, 3)}
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
    for record in latest(run / "traces.jsonl"):
        task = tasks[record["task_id"]]
        scored = score(task, record)
        if record["status"] in NOT_SCORED:
            scored["pass"] = scored["trajectory_pass"] = None
        rows.append({"task_id": task["id"], "sample": record["sample"], "mode": task["mode"],
                     "category": task["category"], "status": record["status"],
                     "stop": record.get("stop"), "seconds": record["seconds"],
                     "tokens": record.get("tokens"), "tags": task.get("tags") or []}
                    | scored)
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
        "statuses": {s: sum(r["status"] == s for r in rows) for s in sorted({r["status"] for r in rows})},
        "judge_pending": sum(r["judge_needed"] for r in rows),
        "seconds_mean": round(sum(r["seconds"] for r in rows) / max(len(rows), 1), 1),
        "tokens_mean": {k: round(sum((r["tokens"] or {}).get(k, 0) for r in rows) / max(len(rows), 1))
                        for k in ("input", "output")},
    }
    (run / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("overall", "by_mode", "outcome_checks", "trajectory_checks", "statuses")}, indent=1))


if __name__ == "__main__":
    main()
