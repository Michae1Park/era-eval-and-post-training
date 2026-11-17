import argparse
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from scipy.stats import spearmanr
from sklearn.metrics import cohen_kappa_score

HERE = Path(__file__).resolve().parent
HUMAN = HERE / "human.jsonl"
DIMENSIONS = ("covered", "grounded", "safe")


def items(row: dict, verdict: dict) -> dict[str, bool]:
    out = {f"{row['task_id']}#{row['sample']}#grounded": verdict["grounded"],
           f"{row['task_id']}#{row['sample']}#safe": verdict["safe"]}
    for i, c in enumerate(verdict["covered"]):
        out[f"{row['task_id']}#{row['sample']}#covered{i}"] = c
    return out


def dimension(key: str) -> str:
    return next(d for d in DIMENSIONS if key.rsplit("#", 1)[1].startswith(d))


def krippendorff_nominal(units: list[list]) -> float | None:
    pairs = defaultdict(float)
    for values in units:
        m = len(values)
        if m < 2:
            continue
        for a in values:
            for b in values:
                pairs[(a, b)] += 1 / (m - 1)
    for values in units:
        if len(values) >= 2:
            for a in values:
                pairs[(a, a)] -= 1 / (len(values) - 1)
    n_c = defaultdict(float)
    for (a, _), w in pairs.items():
        n_c[a] += w
    n = sum(n_c.values())
    if n <= 1:
        return None
    observed = sum(w for (a, b), w in pairs.items() if a != b) / n
    expected = sum(n_c[a] * n_c[b] for a in n_c for b in n_c if a != b) / (n * (n - 1))
    return None if expected == 0 else round(1 - observed / expected, 3)


def kappa(a: list[bool], b: list[bool]) -> float | None:
    if len(a) < 2 or len(set(a) | set(b)) < 2:
        return None
    return round(float(cohen_kappa_score(a, b)), 3)


def per_dimension(fn, labels_a: dict, labels_b: dict) -> dict:
    out = {}
    for d in DIMENSIONS:
        keys = [k for k in labels_a if k in labels_b and dimension(k) == d]
        out[d] = {"n": len(keys), "value": fn([labels_a[k] for k in keys], [labels_b[k] for k in keys])}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", help="results/<label>/<split> with judgments.jsonl")
    ap.add_argument("--probe", default="qwen", help="judge from the agent's model family")
    args = ap.parse_args()
    run = Path(args.run).resolve()
    rows = [json.loads(l) for l in (run / "judgments.jsonl").open()]
    traces = {}
    for line in (run / "traces.jsonl").open():
        r = json.loads(line)
        traces[(r["task_id"], r["sample"])] = r
    labels = defaultdict(dict)
    for row in rows:
        for name, verdict in row["verdicts"].items():
            if "error" not in verdict:
                labels[name] |= items(row, verdict)
    panel = sorted(n for n in labels if n != args.probe)
    out = {"judges": {n: len(labels[n]) for n in labels}}
    out["judge_vs_judge"] = {f"{a}~{b}": per_dimension(kappa, labels[a], labels[b]) for a, b in combinations(panel, 2)}
    out["krippendorff_alpha"] = {}
    for d in DIMENSIONS:
        keys = {k for n in panel for k in labels[n] if dimension(k) == d}
        out["krippendorff_alpha"][d] = krippendorff_nominal([[labels[n][k] for n in panel if k in labels[n]] for k in keys])
    if HUMAN.exists():
        human = {}
        for line in HUMAN.open():
            h = json.loads(line)
            human |= items(h, h)
        majority = {}
        for row in rows:
            majority |= items(row, {"covered": [bool(c) for c in row["panel"]["covered"]],
                                    "grounded": bool(row["panel"]["grounded"]), "safe": bool(row["panel"]["safe"])})
        out["judge_vs_human"] = {n: per_dimension(kappa, labels[n], human) for n in panel}
        out["judge_vs_human"]["panel"] = per_dimension(kappa, majority, human)
    lengths, tones = [], []
    for row in rows:
        tone = row["panel"]["tone"]
        answer = (traces.get((row["task_id"], row["sample"])) or {}).get("answer")
        text = answer.get("answer") if isinstance(answer, dict) else answer
        if tone and text:
            lengths.append(len(text))
            tones.append(tone)
    out["verbosity_bias"] = {"n": len(tones), "spearman_length_tone": round(float(spearmanr(lengths, tones).statistic), 3) if len(tones) > 2 else None}
    if args.probe in labels:
        def pass_rate(name):
            vals = [v for k, v in labels[name].items()]
            return round(sum(vals) / len(vals), 3) if vals else None
        out["self_preference"] = {"probe": args.probe, "probe_positive_rate": pass_rate(args.probe),
                                  "panel_positive_rate": {n: pass_rate(n) for n in panel}}
    (run / "judge-agreement.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
