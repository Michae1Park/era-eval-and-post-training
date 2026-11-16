import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TASKS = ROOT / "bench" / "tasks"
RESULTS = ROOT / "results"
RUNNABLE = {"ask", "research", "investigate", "multi_turn", "report"}


@dataclass
class Context:
    factory: object
    db: Path
    out: Path
    result_chars: int
    retrieval: dict

    def report_search(self):
        from era_agent.asof import AsOf
        from era_agent.retrieval.search import SubQuestionRetriever
        from era_agent.store import Store

        return SubQuestionRetriever.from_settings(Store(self.db, AsOf.today()), self.retrieval)


def git_commit(repo: Path) -> str:
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", "src"],
                           capture_output=True, text=True, check=True).stdout.strip()
    return head + ("-dirty" if dirty else "")


def load_tasks(split: str, modes: set, ids: set | None, limit: int | None) -> list[dict]:
    tasks = [json.loads(line) for line in (TASKS / f"{split}.jsonl").open()]
    tasks = [t for t in tasks if t["mode"] in modes and (not ids or t["id"] in ids)]
    return tasks[:limit] if limit else tasks


def setup(config: dict, out: Path) -> Context:
    repo = (ROOT / config["agent_repo"]).resolve()
    os.environ.setdefault("ERA_COMPANIES", str(repo / config["companies"]))
    os.environ.setdefault("ERA_TELEMETRY", "0")
    os.chdir(repo)
    from era_agent.agent.factory import agent_factory

    retrieval = yaml.safe_load((repo / config["retrieval"]).read_text())["retrieval"]
    retrieval["device"] = config.get("device", retrieval["device"])
    db = repo / config["db"]
    factory = agent_factory(db, retrieval, config["generation"], config["agent"])
    return Context(factory, db, out, config["trace_result_chars"], retrieval)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "test", "train"])
    ap.add_argument("--modes", default="ask,research,investigate,multi_turn")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--label", required=True)
    ap.add_argument("--config", default=str(HERE / "config.yaml"))
    ap.add_argument("--workers", type=int)
    args = ap.parse_args()

    config = yaml.safe_load(Path(args.config).read_text())
    repo = (ROOT / config["agent_repo"]).resolve()
    manifest = json.loads((ROOT / "bench" / "manifest.json").read_text())
    commit = git_commit(repo)
    out = RESULTS / args.label / args.split
    out.mkdir(parents=True, exist_ok=True)
    traces = out / "traces.jsonl"

    modes = set(args.modes.split(",")) & RUNNABLE
    tasks = load_tasks(args.split, modes, set(args.ids or []), args.limit)
    done = set()
    if traces.exists():
        for line in traces.open():
            row = json.loads(line)
            if row["status"] == "ok":
                done.add((row["task_id"], row["sample"]))
    todo = [(t, s) for t in tasks for s in range(args.k) if (t["id"], s) not in done]

    run_info = {"label": args.label, "split": args.split, "agent_commit": commit,
                "bench_version": manifest["version"], "bench_sha256_16": manifest["sha256_16"],
                "config": config, "k": args.k, "modes": sorted(modes),
                "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "tasks": len(tasks), "todo": len(todo)}
    (out / "run.json").write_text(json.dumps(run_info, indent=2))
    print(f"{len(todo)} runs ({len(tasks)} tasks x k={args.k}, {len(done)} done) -> {traces}")

    sys.path.insert(0, str(HERE))
    from adapters import execute

    ctx = setup(config, out)
    stamp = {"agent_commit": commit, "bench_sha256_16": manifest["sha256_16"],
             "config_sha256_16": hashlib.sha256(json.dumps(config, sort_keys=True).encode())
             .hexdigest()[:16]}
    lock = threading.Lock()
    counter = {"n": 0}

    def work(item):
        task, sample = item
        record = execute(ctx, task, sample) | stamp
        with lock, traces.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            counter["n"] += 1
            print(f"[{counter['n']}/{len(todo)}] {task['id']}#{sample} {record['status']} "
                  f"{record.get('stop', '')} {record['seconds']}s", flush=True)

    serial = [i for i in todo if i[0]["mode"] == "report"]
    parallel = [i for i in todo if i[0]["mode"] != "report"]
    with ThreadPoolExecutor(args.workers or config["workers"]) as pool:
        list(pool.map(work, parallel))
    for item in serial:
        work(item)


if __name__ == "__main__":
    main()
