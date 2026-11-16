import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

BENCH_VERSION = "0.1.0"
BENCH_DIR = Path(__file__).parent
GOLD_DIR = Path("evaluation/gold")

FY2025_SOURCE = "agent-gold-fy2025.jsonl"
RETRIEVAL_SOURCE = "retrieval-gold-fy2025.jsonl"
GENERATION_SOURCE = "generation-gold-fy2025.jsonl"
FY2025_COMPANIES = ["AAPL", "AMZN", "MSFT", "NVDA"]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def ids_in(path: Path) -> set[str]:
    return {row["id"] for row in read_jsonl(path)}


def answer_block(row: dict) -> dict:
    expected = row.get("expected_answer")
    values = expected if isinstance(expected, list) else [expected] if expected else []
    return {
        "type": row.get("answer_type"),
        "values": values,
        "tolerance": row.get("tolerance"),
        "should_abstain": row.get("should_abstain", False),
    }


def review_block(row: dict) -> dict:
    return {
        "origin": row.get("origin"),
        "verified_by": row.get("verified_by") or None,
        "verified_on": row.get("verified_on"),
    }


def provenance(source_file: str, source_id: str, agent_commit: str) -> dict:
    return {"repo": "equity-research-agent", "commit": agent_commit, "file": source_file, "id": source_id}


def companies_of(row: dict) -> list[str]:
    if row.get("companies"):
        return sorted(row["companies"])
    if row.get("company"):
        return [row["company"]]
    named = {s["company"] for s in row.get("sources", []) if s.get("company")}
    named |= {v["company"] for v in answer_block(row)["values"] if isinstance(v, dict) and v.get("company")}
    return sorted(named)


def fy2025_tasks(gold: Path, commit: str) -> list[dict]:
    retrieval_ids = ids_in(gold / RETRIEVAL_SOURCE)
    generation_ids = ids_in(gold / GENERATION_SOURCE)
    tasks = []
    for row in read_jsonl(gold / FY2025_SOURCE):
        layers = ["e2e", "trajectory"]
        if row["id"] in generation_ids:
            layers.append("generation")
        if row["id"] in retrieval_ids:
            layers.append("retrieval")
        tasks.append({
            "id": f"fy25-{row['id']}",
            "suite": "fy2025",
            "mode": "ask_fy2025",
            "layers": sorted(layers),
            "category": row["category"],
            "kind": row.get("kind"),
            "split": row["split"],
            "as_of": None,
            "companies": companies_of(row) or FY2025_COMPANIES,
            "question": row["question"],
            "answer": answer_block(row),
            "required_points": row.get("required_points", []),
            "expected_gaps": [],
            "expected_refs": [],
            "expected_tools": row.get("expected_tools", []),
            "evidence": {"gold": row.get("sources", []), "acceptable": row.get("acceptable_sources", [])},
            "parts": [],
            "requires_assumptions": False,
            "failure_mode": row.get("failure_mode"),
            "review": review_block(row),
            "provenance": provenance(FY2025_SOURCE, row["id"], commit),
        })
    return tasks


def ask_tasks(gold: Path, commit: str) -> list[dict]:
    source = "ask-gold.jsonl"
    return [{
        "id": f"ask-{row['id']}",
        "suite": "marketplaces",
        "mode": "ask",
        "layers": ["e2e", "trajectory"],
        "category": row["category"],
        "kind": row.get("kind"),
        "split": row["split"],
        "as_of": row.get("as_of"),
        "companies": companies_of(row),
        "question": row["question"],
        "answer": answer_block(row),
        "required_points": row.get("required_points", []),
        "expected_gaps": [],
        "expected_refs": [],
        "expected_tools": row.get("expected_tools", []),
        "evidence": {"gold": row.get("sources", []), "acceptable": []},
        "parts": [],
        "requires_assumptions": False,
        "failure_mode": row.get("failure_mode"),
        "review": review_block(row),
        "provenance": provenance(source, row["id"], commit),
    } for row in read_jsonl(gold / source)]


def research_tasks(gold: Path, commit: str) -> list[dict]:
    source = "research-gold.jsonl"
    return [{
        "id": f"research-{row['id']}",
        "suite": "marketplaces",
        "mode": "research",
        "layers": ["e2e", "trajectory"],
        "category": row["category"],
        "kind": None,
        "split": row["split"],
        "as_of": row.get("as_of"),
        "companies": companies_of(row),
        "question": row["question"],
        "answer": {"type": "model_ref", "values": [], "tolerance": None, "should_abstain": False},
        "required_points": [],
        "expected_gaps": [],
        "expected_refs": row.get("expected_refs", []),
        "expected_tools": row.get("expected_tools", []),
        "evidence": {"gold": [], "acceptable": []},
        "parts": [],
        "requires_assumptions": row.get("requires_assumptions", False),
        "failure_mode": None,
        "review": review_block(row),
        "provenance": provenance(source, row["id"], commit),
    } for row in read_jsonl(gold / source)]


def investigate_tasks(gold: Path, commit: str) -> list[dict]:
    source = "investigate-gold.jsonl"
    return [{
        "id": f"investigate-{row['id']}",
        "suite": "marketplaces",
        "mode": "investigate",
        "layers": ["e2e", "trajectory"],
        "category": row["category"],
        "kind": None,
        "split": row["split"],
        "as_of": row.get("as_of"),
        "companies": companies_of(row),
        "question": row["question"],
        "answer": {"type": "composite", "values": [], "tolerance": row.get("tolerance"), "should_abstain": False},
        "required_points": row.get("required_points", []),
        "expected_gaps": row.get("expected_gaps", []),
        "expected_refs": [],
        "expected_tools": [],
        "evidence": {"gold": [], "acceptable": []},
        "parts": row.get("parts", []),
        "requires_assumptions": row.get("requires_assumptions", False),
        "failure_mode": None,
        "review": review_block(row),
        "provenance": provenance(source, row["id"], commit),
    } for row in read_jsonl(gold / source)]


def extraction_tasks(gold: Path, commit: str) -> list[dict]:
    source = "extraction-gold.jsonl"
    return [{
        "id": f"extract-{row['id']}",
        "suite": "marketplaces",
        "mode": "extraction",
        "layers": ["extraction"],
        "category": row["metric"],
        "kind": row.get("segment"),
        "split": "test",
        "as_of": None,
        "companies": [row["ticker"]],
        "question": None,
        "answer": {
            "type": "number",
            "values": [{"value": row["value"], "unit": row["unit"], "company": row["ticker"],
                        "period": row.get("target_period") or row["period"]}],
            "tolerance": 0.0,
            "should_abstain": False,
        },
        "required_points": [],
        "expected_gaps": [],
        "expected_refs": [],
        "expected_tools": [],
        "evidence": {"gold": [{"source": row["source"], "block": row.get("block"), "evidence": row.get("quote")}],
                     "acceptable": []},
        "parts": [],
        "requires_assumptions": False,
        "failure_mode": None,
        "review": {"origin": "crosscheck", "verified_by": row.get("verified_by"), "verified_on": None},
        "provenance": provenance(source, row["id"], commit),
    } for row in read_jsonl(gold / source)]


def human_verified(task: dict) -> bool:
    verifier = task["review"]["verified_by"] or ""
    return bool(verifier) and not verifier.startswith("claude")


def coverage_markdown(tasks: list[dict], commit: str) -> str:
    by_mode = Counter(t["mode"] for t in tasks)
    lines = [
        f"# ERA-Bench v{BENCH_VERSION} coverage",
        "",
        f"Generated by `bench/build.py` from equity-research-agent `{commit}`. Do not edit by hand.",
        "",
        "| Mode | Tasks | dev | test | Human-verified | Retrieval gold | Abstain |",
        "|---|---|---|---|---|---|---|",
    ]
    for mode in by_mode:
        subset = [t for t in tasks if t["mode"] == mode]
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            mode,
            len(subset),
            sum(t["split"] == "dev" for t in subset),
            sum(t["split"] == "test" for t in subset),
            sum(human_verified(t) for t in subset),
            sum("retrieval" in t["layers"] for t in subset),
            sum(t["answer"]["should_abstain"] for t in subset),
        ))
    lines.append(f"| **total** | **{len(tasks)}** | | | **{sum(human_verified(t) for t in tasks)}** | | |")
    lines += ["", "## Categories by mode", ""]
    for mode in by_mode:
        counts = Counter(t["category"] for t in tasks if t["mode"] == mode)
        lines.append(f"- **{mode}**: " + ", ".join(f"{c} {n}" for c, n in counts.most_common()))
    return "\n".join(lines) + "\n"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("agent_repo", type=Path)
    args = parser.parse_args()

    gold = args.agent_repo / GOLD_DIR
    commit = subprocess.check_output(["git", "-C", str(args.agent_repo), "rev-parse", "--short", "HEAD"], text=True).strip()

    tasks = (fy2025_tasks(gold, commit) + ask_tasks(gold, commit) + research_tasks(gold, commit)
             + investigate_tasks(gold, commit) + extraction_tasks(gold, commit))
    ids = [t["id"] for t in tasks]
    duplicates = [i for i, n in Counter(ids).items() if n > 1]
    if duplicates:
        raise SystemExit(f"duplicate task ids: {duplicates[:5]}")

    out = BENCH_DIR / "tasks"
    out.mkdir(exist_ok=True)
    for mode in sorted({t["mode"] for t in tasks}):
        write_jsonl(out / f"{mode}.jsonl", [t for t in tasks if t["mode"] == mode])

    digest = hashlib.sha256("".join(json.dumps(t, sort_keys=True) for t in tasks).encode()).hexdigest()[:16]
    manifest = {"version": BENCH_VERSION, "agent_commit": commit, "tasks": len(tasks), "sha256_16": digest}
    (BENCH_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (BENCH_DIR / "COVERAGE.md").write_text(coverage_markdown(tasks, commit))
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
