import argparse
import json
import os
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASKS = ROOT / "eval" / "bench" / "tasks"
RESULTS = ROOT / "results"
PROMPT = """Answer the question using only the context. If the context does not contain the answer, say so.

Context:
{context}

Question: {question}

Reply with only JSON: {{"answer": "one or two sentences", "claims": [{{"value": number, "unit": "USD millions | USD | percent | ...", "company": "TICKER"}}]}}"""


def gold_children(task: dict) -> list[str]:
    return list(task["evidence"].get("chunk_ids") or []) + [i for p in task.get("parts") or [] for i in p.get("chunk_ids") or []]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--config", default=str(ROOT / "eval" / "harness" / "config.yaml"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--set", nargs="*", default=[])
    args = ap.parse_args()
    config = yaml.safe_load(Path(args.config).read_text())
    for item in args.set:
        path, _, value = item.partition("=")
        *parents, leaf = path.split(".")
        node = config
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = yaml.safe_load(value)
    repo = (ROOT / config["agent_repo"]).resolve()
    os.environ.setdefault("ERA_COMPANIES", str(repo / config["companies"]))
    os.chdir(repo)
    sys.path.insert(0, str(HERE))
    import openai
    from rules import numbers

    db = sqlite3.connect(repo / config["db"], check_same_thread=False)
    gen = config["generation"]
    client = openai.OpenAI(api_key="not-needed", base_url=gen["base_url"], max_retries=4)
    model = gen["model"].partition(":")[2]
    tasks = [json.loads(l) for l in (TASKS / f"{args.split}.jsonl").open()]
    tasks = [t for t in tasks if gold_children(t) and t["answer"].get("values") and t.get("question")]

    def one(task: dict) -> dict:
        ids = gold_children(task)
        texts = [r[0] for i in ids for r in db.execute("select text from children where id=?", (i,))]
        prompt = PROMPT.format(context="\n\n---\n\n".join(texts), question=task["question"])
        reply = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}], max_completion_tokens=gen["max_tokens"],
            temperature=0, extra_body={"chat_template_kwargs": {"enable_thinking": gen.get("thinking", False)}})
        text = reply.choices[0].message.content or ""
        match = re.search(r"\{.*\}", text, re.DOTALL)
        try:
            answer = json.loads(match.group(0)) if match else {"answer": text}
        except json.JSONDecodeError:
            answer = {"answer": text}
        ok = numbers(task["answer"]["values"], answer, task["answer"].get("tolerance") or 0.005)
        return {"task_id": task["id"], "mode": task["mode"], "category": task["category"], "answer": answer, "pass": ok}

    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(one, tasks))
    out = RESULTS / args.label / args.split
    out.mkdir(parents=True, exist_ok=True)
    with (out / "generation.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    passed = [r["pass"] for r in rows if r["pass"] is not None]
    summary = {"tasks": len(passed), "pass_rate_gold_context": round(sum(passed) / max(len(passed), 1), 3),
               "by_category": {c: round(sum(r["pass"] for r in rows if r["category"] == c and r["pass"] is not None)
                                        / max(sum(r["category"] == c and r["pass"] is not None for r in rows), 1), 3)
                               for c in sorted({r["category"] for r in rows})}}
    (out / "generation-summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
