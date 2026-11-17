import argparse
import hashlib
import json
import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from agents import AGENTS  # noqa: E402
from agents.base import TRACE_SCHEMA, RunContext  # noqa: E402
from runtime import AGENT_STATUSES, TaskCancelled, cancel_all, execute  # noqa: E402

ROOT = HERE.parent.parent
TASKS = HERE.parent / "bench" / "tasks"
RESULTS = ROOT / "results"
REGISTRY = RESULTS / "runs.jsonl"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_tasks(split: str, modes: set, ids: set, limit: int | None) -> list[dict]:
    tasks = [json.loads(line) for line in (TASKS / f"{split}.jsonl").open()]
    tasks = [t for t in tasks if t["mode"] in modes and (not ids or t["id"] in ids)]
    return tasks[:limit] if limit else tasks


def finished(traces: Path) -> set:
    done = set()
    if traces.exists():
        for line in traces.open():
            row = json.loads(line)
            key = (row["task_id"], row["sample"])
            (done.add if row["status"] in AGENT_STATUSES else done.discard)(key)
    return done


def register(entry: dict) -> None:
    RESULTS.mkdir(exist_ok=True)
    with REGISTRY.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def interrupt(signum, frame):
    raise KeyboardInterrupt


def main() -> None:
    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--split", default="dev", choices=["dev", "test", "train"])
    ap.add_argument("--modes", default="ask,research,investigate,multi_turn")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--config", default=str(HERE / "config.yaml"))
    ap.add_argument("--workers", type=int)
    ap.add_argument("--set", nargs="*", default=[], help="config overrides, e.g. generation.model=openai:Qwen/Qwen3.5-9B")
    args = ap.parse_args()

    config = yaml.safe_load(Path(args.config).read_text())
    for item in args.set:
        path, _, value = item.partition("=")
        *parents, leaf = path.split(".")
        node = config
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = yaml.safe_load(value)
    agent = AGENTS[config["agent_under_test"]]()
    agent.configure(config)
    version = agent.version()
    manifest = json.loads((HERE.parent / "bench" / "manifest.json").read_text())
    out = RESULTS / args.label / args.split
    out.mkdir(parents=True, exist_ok=True)
    traces = out / "traces.jsonl"

    modes = set(args.modes.split(",")) & agent.modes
    tasks = load_tasks(args.split, modes, set(args.ids or []), args.limit)
    done = finished(traces)
    todo = [(t, s) for t in tasks for s in range(args.k) if (t["id"], s) not in done]
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
    stamp = {"trace_schema": TRACE_SCHEMA, "agent": agent.name, "agent_version": version,
             "bench_version": manifest["version"], "bench_sha256_16": manifest["sha256_16"], "config_sha256_16": config_hash}
    run_id = f"{args.label}/{args.split}@{now()}"
    run_info = {"run_id": run_id, "label": args.label, "split": args.split, "k": args.k, "modes": sorted(modes),
                "tasks": len(tasks), "todo": len(todo), "started": now(), "config": config} | stamp
    (out / "run.json").write_text(json.dumps(run_info, indent=2))
    register({"event": "start"} | {k: v for k, v in run_info.items() if k != "config"})
    print(f"{len(todo)} runs ({len(tasks)} tasks x k={args.k}, {len(done)} done) -> {traces}", flush=True)

    agent.setup(config, RunContext(out, config["trace_result_chars"]))
    lock = threading.Lock()
    counts: dict[str, int] = {}

    def work(item):
        task, sample = item
        try:
            record = execute(agent, task, sample, config["timeout_seconds"][task["mode"]], config["retries"],
                             config["backoff_seconds"]) | stamp
        except TaskCancelled:
            return
        with lock, traces.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            counts[record["status"]] = counts.get(record["status"], 0) + 1
            print(f"[{sum(counts.values())}/{len(todo)}] {task['id']}#{sample} {record['status']} "
                  f"{record.get('stop', '')} {record['seconds']}s", flush=True)

    status = "finished"
    pool = ThreadPoolExecutor(args.workers or config["workers"])
    try:
        futures = [pool.submit(work, i) for i in todo if i[0]["mode"] != "report"]
        wait(futures)
        for item in [i for i in todo if i[0]["mode"] == "report"]:
            work(item)
    except KeyboardInterrupt:
        status = "cancelled"
        cancel_all.set()
        print("cancelling: finishing the current model or tool call, keeping written traces", flush=True)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        register({"event": status, "run_id": run_id, "ended": now(), "counts": counts})
    print(json.dumps({"status": status, "counts": counts}))


if __name__ == "__main__":
    main()
