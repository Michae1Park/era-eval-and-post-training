import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import bootstrap
from statsmodels.stats.contingency_tables import mcnemar


def task_means(run: Path) -> dict[str, tuple[str, float]]:
    samples = defaultdict(list)
    modes = {}
    for line in (run / "scores.jsonl").open():
        row = json.loads(line)
        if row["pass"] is not None:
            samples[row["task_id"]].append(row["pass"])
            modes[row["task_id"]] = row["mode"]
    return {t: (modes[t], sum(s) / len(s)) for t, s in samples.items()}


def paired(a: list[float], b: list[float]) -> dict:
    a, b = np.array(a), np.array(b)
    diff = b - a
    out = {"tasks": len(a), "a": round(a.mean(), 3), "b": round(b.mean(), 3), "delta": round(diff.mean(), 3)}
    if len(a) >= 2 and len(set(diff)) > 1:
        ci = bootstrap((diff,), np.mean, n_resamples=10000, method="percentile", random_state=0).confidence_interval
        out["delta_ci95"] = (round(float(ci.low), 3), round(float(ci.high), 3))
    fixed, broke = int(((a < 0.5) & (b >= 0.5)).sum()), int(((a >= 0.5) & (b < 0.5)).sum())
    both = int(((a >= 0.5) & (b >= 0.5)).sum())
    neither = len(a) - fixed - broke - both
    out |= {"fixed": fixed, "broke": broke,
            "mcnemar_p": round(float(mcnemar([[both, broke], [fixed, neither]], exact=True).pvalue), 4)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a", type=Path, help="results/<label>/<split> (baseline)")
    ap.add_argument("b", type=Path, help="results/<label>/<split> (candidate)")
    args = ap.parse_args()
    a, b = task_means(args.a), task_means(args.b)
    shared = sorted(set(a) & set(b))
    by_mode = defaultdict(list)
    for t in shared:
        by_mode[a[t][0]].append(t)
    report = {"a": str(args.a), "b": str(args.b), "only_in_a": len(set(a) - set(b)), "only_in_b": len(set(b) - set(a)),
              "overall": paired([a[t][1] for t in shared], [b[t][1] for t in shared]),
              "by_mode": {m: paired([a[t][1] for t in ts], [b[t][1] for t in ts]) for m, ts in sorted(by_mode.items())},
              "fixed": [t for t in shared if a[t][1] < 0.5 <= b[t][1]],
              "broke": [t for t in shared if b[t][1] < 0.5 <= a[t][1]]}
    out = args.b / f"compare-{args.a.parent.name}.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("overall", "by_mode")}, indent=1))


if __name__ == "__main__":
    main()
