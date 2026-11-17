import argparse
import json
import math
import os
from pathlib import Path

import numpy as np
import yaml
from scipy.stats import bootstrap

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "eval" / "bench" / "tasks"
RESULTS = ROOT / "results"
KS = (1, 5, 8)


def parent(chunk_id: str) -> str:
    return chunk_id.rsplit("-c", 1)[0]


def gold_of(task: dict) -> set[str]:
    ids = list(task["evidence"].get("chunk_ids") or []) + [i for p in task.get("parts") or [] for i in p.get("chunk_ids") or []]
    return {parent(i) for i in ids}


def metrics(retrieved: list[str], gold: set[str]) -> dict:
    out = {f"recall@{k}": len(gold & set(retrieved[:k])) / len(gold) for k in KS}
    out |= {f"hit@{k}": float(bool(gold & set(retrieved[:k]))) for k in KS}
    rank = next((i for i, cid in enumerate(retrieved, 1) if cid in gold), None)
    out["mrr"] = 1 / rank if rank else 0.0
    k = max(KS)
    dcg = sum(1 / math.log2(i + 1) for i, cid in enumerate(retrieved[:k], 1) if cid in gold)
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(len(gold), k) + 1))
    out[f"ndcg@{k}"] = dcg / ideal
    return out


def ci(values: list[float]) -> list[float]:
    if len(values) < 2 or len(set(values)) == 1:
        return [round(values[0], 3)] * 2 if values else [None, None]
    r = bootstrap((np.array(values),), np.mean, n_resamples=5000, method="percentile", random_state=0)
    return [round(float(r.confidence_interval.low), 3), round(float(r.confidence_interval.high), 3)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--label", default="retrieval-baseline")
    ap.add_argument("--config", default=str(ROOT / "eval" / "harness" / "config.yaml"))
    ap.add_argument("--set", nargs="*", default=[], help="retrieval overrides, e.g. candidates=20 k=8")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    config = yaml.safe_load(Path(args.config).read_text())
    repo = (ROOT / config["agent_repo"]).resolve()
    os.environ.setdefault("ERA_COMPANIES", str(repo / config["companies"]))
    os.chdir(repo)
    from era_agent.asof import AsOf
    from era_agent.retrieval.search import SubQuestionRetriever
    from era_agent.store import Store

    settings = yaml.safe_load((repo / config["retrieval"]).read_text())["retrieval"]
    settings["device"] = config.get("device", settings["device"])
    for item in args.set:
        key, _, value = item.partition("=")
        settings[key] = yaml.safe_load(value)
    db = repo / config["db"]
    tasks = [json.loads(l) for l in (TASKS / f"{args.split}.jsonl").open()]
    tasks = [t for t in tasks if gold_of(t) and t.get("question")][: args.limit]
    retrievers: dict[str, SubQuestionRetriever] = {}
    rows = []
    for i, task in enumerate(tasks, 1):
        if task["as_of"] not in retrievers:
            retrievers[task["as_of"]] = SubQuestionRetriever.from_settings(Store(db, AsOf.of(task["as_of"])), settings)
        result = retrievers[task["as_of"]].search(task["question"], max(max(KS), settings.get("k", 8)),
                                                  tickers=task["companies"] or None)
        retrieved = [c.id for c in result.chunks]
        rows.append({"task_id": task["id"], "mode": task["mode"], "category": task["category"],
                     "gold": sorted(gold_of(task)), "retrieved": retrieved} | metrics(retrieved, gold_of(task)))
        if i % 25 == 0:
            print(f"{i}/{len(tasks)}", flush=True)
    out = RESULTS / args.label / args.split
    out.mkdir(parents=True, exist_ok=True)
    with (out / "retrieval.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    names = [f"hit@{k}" for k in KS] + [f"recall@{k}" for k in KS] + ["mrr", f"ndcg@{max(KS)}"]
    summary = {"queries": len(rows), "settings": settings,
               "overall": {n: {"mean": round(sum(r[n] for r in rows) / len(rows), 3), "ci95": ci([r[n] for r in rows])} for n in names},
               "by_mode": {m: {n: round(sum(r[n] for r in rows if r["mode"] == m) / sum(r["mode"] == m for r in rows), 3) for n in names}
                           for m in sorted({r["mode"] for r in rows})},
               "by_category": {c: {"n": sum(r["category"] == c for r in rows), f"hit@{max(KS)}": round(sum(r[f"hit@{max(KS)}"] for r in rows if r["category"] == c) / sum(r["category"] == c for r in rows), 3)}
                               for c in sorted({r["category"] for r in rows})}}
    (out / "retrieval-summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("queries", "overall", "by_mode")}, indent=1))


if __name__ == "__main__":
    main()
