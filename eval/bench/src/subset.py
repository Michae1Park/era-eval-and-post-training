import argparse
import json
from collections import defaultdict
from pathlib import Path

from schema import stable_fraction

TASKS = Path(__file__).resolve().parents[1] / "tasks"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--size", type=int, default=150)
    args = ap.parse_args()
    tasks = [json.loads(l) for l in (TASKS / f"{args.split}.jsonl").open() if json.loads(l)["mode"] != "report"]
    strata = defaultdict(list)
    for t in tasks:
        strata[(t["mode"], t["category"])].append(t["id"])
    picked = []
    for ids in strata.values():
        ids.sort(key=stable_fraction)
        picked += ids[:max(1, round(len(ids) * args.size / len(tasks)))]
    path = TASKS / f"{args.split}-subset.txt"
    path.write_text("\n".join(sorted(picked)) + "\n")
    print(f"{len(picked)} tasks from {len(strata)} strata -> {path}")


if __name__ == "__main__":
    main()
