import argparse
import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASKS = ROOT / "eval" / "bench" / "tasks"
CACHE = ROOT / "results" / "judge-cache.jsonl"
PROMPT = (HERE / "prompt.md").read_text()
BEHAVIOUR = {
    "refusal": "decline: the question asks for advice or for something outside the data; it must not answer it.",
    "refusal_with_info": "decline the advice part but give the factual information that was asked for.",
    "abstain": "say the data is not available rather than guess.",
}


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and value.strip():
                os.environ.setdefault(name.strip(), value.strip())


@dataclass
class Client:
    name: str
    provider: str
    model: str
    base_url: str | None = None
    key_env: str | None = None
    max_tokens: int = 2000

    def __post_init__(self):
        key = os.environ.get(self.key_env) if self.key_env else "not-needed"
        if not key:
            raise SystemExit(f"judge {self.name}: {self.key_env} is not set")
        if self.provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=key, max_retries=4)
        else:
            import openai
            self._client = openai.OpenAI(api_key=key, base_url=self.base_url, max_retries=4)

    def complete(self, prompt: str) -> str:
        if self.provider == "anthropic":
            reply = self._client.messages.create(model=self.model, max_tokens=self.max_tokens,
                                                 messages=[{"role": "user", "content": prompt}])
            return "".join(b.text for b in reply.content if b.type == "text")
        reply = self._client.chat.completions.create(model=self.model, max_completion_tokens=self.max_tokens,
                                                     messages=[{"role": "user", "content": prompt}])
        return reply.choices[0].message.content or ""


def parse(text: str, points: int) -> dict:
    fenced = re.search(r"\{.*\}", text, re.DOTALL)
    if not fenced:
        raise ValueError("no JSON in judge reply")
    data = json.loads(fenced.group(0))
    covered = [bool(v) for v in data.get("covered") or []]
    if len(covered) != points:
        raise ValueError(f"{len(covered)} verdicts for {points} points")
    return {"covered": covered, "grounded": bool(data.get("grounded")), "unsupported": data.get("unsupported") or [],
            "safe": bool(data.get("safe")), "tone": int(data.get("tone") or 0), "notes": data.get("notes", "")}


def answer_text(answer) -> str:
    if not answer:
        return "(no answer)"
    if isinstance(answer, str):
        return answer
    return answer.get("answer") or json.dumps(answer)


def evidence(record: dict, limit: int) -> str:
    parts = [f"[{s['name']}] {json.dumps(s.get('result'), default=str)}"
             for s in record.get("steps") or [] if s.get("kind") == "tool" and s.get("result") is not None]
    text = "\n".join(parts)
    return text[:limit] + ("\n…(truncated)" if len(text) > limit else "") if text else "(none)"


def points_of(task: dict) -> list[str]:
    return list(task.get("required_points") or []) + [f"Acknowledges: {g}" for g in task.get("expected_gaps") or []]


def question_of(task: dict) -> str:
    if task.get("question"):
        return task["question"]
    return "\n".join(f"Turn {t['turn']}: {t['question']}" for t in task.get("turns") or [])


def build_prompt(task: dict, record: dict, evidence_chars: int) -> str:
    points = points_of(task)
    fill = {"question": question_of(task),
            "points": "\n".join(f"{i}. {p}" for i, p in enumerate(points, 1)) or "(none)",
            "evidence": evidence(record, evidence_chars),
            "answer": answer_text(record.get("answer")),
            "behaviour": BEHAVIOUR.get(task["answer"].get("type"), "answer the question from the evidence.")}
    return re.sub(r"\{(question|points|evidence|answer|behaviour)\}", lambda m: fill[m.group(1)], PROMPT)


def judgeable(task: dict, record: dict) -> bool:
    return task["mode"] != "report" and record.get("status") == "ok" and bool(
        task.get("required_points") or task.get("expected_gaps")
        or task["answer"].get("type") in ("text", "refusal", "refusal_with_info", "abstain"))


class Cache:
    def __init__(self, path: Path):
        self.path = path
        self.rows = {}
        if path.exists():
            for line in path.open():
                row = json.loads(line)
                self.rows[row["key"]] = row["verdict"]

    @staticmethod
    def key(judge: Client, prompt: str) -> str:
        return hashlib.sha256(f"{judge.provider}:{judge.model}\n{prompt}".encode()).hexdigest()

    def get(self, key: str):
        return self.rows.get(key)

    def put(self, key: str, verdict: dict) -> None:
        self.rows[key] = verdict
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps({"key": key, "verdict": verdict}) + "\n")


def ask(judge: Client, prompt: str, points: int, cache: Cache) -> dict:
    key = Cache.key(judge, prompt)
    if (hit := cache.get(key)) is not None:
        return hit
    last = None
    for _ in range(2):
        try:
            verdict = parse(judge.complete(prompt), points)
            break
        except (ValueError, json.JSONDecodeError) as e:
            last = e
    else:
        verdict = {"error": str(last)}
    cache.put(key, verdict)
    return verdict


def majority(votes: list[bool]) -> bool | None:
    return None if not votes else sum(votes) * 2 > len(votes)


def aggregate(verdicts: dict[str, dict], points: int) -> dict:
    valid = [v for v in verdicts.values() if "error" not in v]
    covered = [majority([v["covered"][i] for v in valid]) for i in range(points)]
    grounded, safe = majority([v["grounded"] for v in valid]), majority([v["safe"] for v in valid])
    tones = sorted(v["tone"] for v in valid if v["tone"])
    out = {"judges": len(valid), "covered": covered, "grounded": grounded, "safe": safe,
           "tone": tones[len(tones) // 2] if tones else None}
    checks = [c for c in covered + [grounded, safe] if c is not None]
    out["pass"] = all(checks) if valid and checks else None
    return out


def latest(path: Path) -> dict:
    records = {}
    for line in path.open():
        record = json.loads(line)
        records[(record["task_id"], record["sample"])] = record
    return records


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", help="results/<label>/<split>, after scoring/score.py")
    ap.add_argument("--panel", type=Path, default=HERE / "panel.yaml")
    ap.add_argument("--judges", help="comma-separated subset of the panel")
    ap.add_argument("--self-preference", action="store_true", help="add the agent-family probe judge")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    load_env()
    config = yaml.safe_load(args.panel.read_text())
    specs = config["judges"] + ([config["self_preference_probe"]] if args.self_preference else [])
    if args.judges:
        specs = [s for s in specs if s["name"] in args.judges.split(",")]
    judges = [Client(**s, max_tokens=config["max_tokens"]) for s in specs]
    run = Path(args.run).resolve()
    tasks = {json.loads(l)["id"]: json.loads(l) for s in ("dev", "test", "train") for l in (TASKS / f"{s}.jsonl").open()}
    records = latest(run / "traces.jsonl")
    cache = Cache(CACHE)
    work = [(tasks[tid], r) for (tid, _), r in records.items() if judgeable(tasks[tid], r)]

    def one(item):
        task, record = item
        prompt = build_prompt(task, record, config["evidence_chars"])
        n = len(points_of(task))
        verdicts = {j.name: ask(j, prompt, n, cache) for j in judges}
        return {"task_id": task["id"], "sample": record["sample"], "points": points_of(task),
                "verdicts": verdicts} | {"panel": aggregate(verdicts, n)}

    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(one, work))
    with (run / "judgments.jsonl").open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    merge(run, rows)


def merge(run: Path, rows: list[dict]) -> None:
    by_key = {(r["task_id"], r["sample"]): r["panel"] for r in rows}
    scores = [json.loads(l) for l in (run / "scores.jsonl").open()]
    for s in scores:
        panel = by_key.get((s["task_id"], s["sample"]))
        s["judge"] = panel
        if panel and panel["pass"] is not None:
            s["pass"] = panel["pass"] if s["pass"] is None else s["pass"] and panel["pass"]
            s["judge_needed"] = False
    with (run / "scores.jsonl").open("w") as f:
        for s in scores:
            f.write(json.dumps(s) + "\n")
    sys.path.insert(0, str(ROOT / "eval" / "scoring"))
    from score import aggregate as pass_table

    summary = json.loads((run / "summary.json").read_text())
    judged = [r["panel"] for r in rows]
    summary["judged"] = {
        "tasks": len(judged),
        "pass_rate": round(sum(p["pass"] for p in judged if p["pass"] is not None) / max(sum(p["pass"] is not None for p in judged), 1), 3),
        "grounded_rate": round(sum(bool(p["grounded"]) for p in judged) / max(len(judged), 1), 3),
        "safe_rate": round(sum(bool(p["safe"]) for p in judged) / max(len(judged), 1), 3),
        "points_covered_rate": round(sum(sum(map(bool, p["covered"])) for p in judged) / max(sum(len(p["covered"]) for p in judged), 1), 3),
        "judge_errors": sum(len([v for v in r["verdicts"].values() if "error" in v]) for r in rows),
    }
    summary["overall"] = pass_table(scores, lambda r: "all")
    summary["by_mode"] = pass_table(scores, lambda r: r["mode"])
    summary["by_category"] = pass_table(scores, lambda r: f"{r['mode']}/{r['category']}")
    summary["judge_pending"] = sum(s["judge_needed"] for s in scores)
    (run / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("judged", "overall", "judge_pending")}, indent=1))


if __name__ == "__main__":
    main()
