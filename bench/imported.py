import json
from pathlib import Path

from schema import task

GOLD_DIR = Path("evaluation/gold")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def review(row: dict) -> dict:
    return {"origin": f"agent-repo:{row.get('origin')}", "verified_by": row.get("verified_by") or None, "verified_on": row.get("verified_on")}


def ordered(tools: list[str]) -> list[dict]:
    return [{"tool": t} for t in tools]


def provenance(file: str, row: dict, commit: str) -> dict:
    return {"repo": "equity-research-agent", "commit": commit, "file": f"{GOLD_DIR}/{file}", "id": row["id"]}


def companies(row: dict) -> list[str]:
    named = set(row.get("companies") or ([row["company"]] if row.get("company") else []))
    named |= {s["company"] for s in row.get("sources", []) if s.get("company")}
    expected = row.get("expected_answer")
    for v in expected if isinstance(expected, list) else [expected] if expected else []:
        if isinstance(v, dict) and v.get("company"):
            named.add(v["company"])
    return sorted(named)


def ask(repo: Path, commit: str) -> list[dict]:
    file = "ask-gold.jsonl"
    out = []
    for row in read_jsonl(repo / GOLD_DIR / file):
        expected = row.get("expected_answer")
        values = expected if isinstance(expected, list) else [expected] if expected else []
        out.append(task(
            id=f"ask-{row['id']}",
            category=row["category"],
            kind=row.get("kind"),
            split=row["split"],
            as_of=row.get("as_of"),
            companies=companies(row),
            question=row["question"],
            answer={"type": row["answer_type"], "values": values, "tolerance": row.get("tolerance", 0.005),
                    "should_abstain": row.get("should_abstain", False)},
            required_points=row.get("required_points", []),
            trajectory={"expected_tools": row.get("expected_tools", []), "ordered": ordered(row.get("expected_tools", []))},
            evidence={"gold": row.get("sources", [])},
            failure_mode=row.get("failure_mode"),
            review=review(row),
            provenance=provenance(file, row, commit),
        ))
    return out


def research(repo: Path, commit: str) -> list[dict]:
    file = "research-gold.jsonl"
    return [task(
        id=f"research-{row['id']}",
        mode="research",
        category=row["category"],
        split=row["split"],
        as_of=row.get("as_of"),
        companies=companies(row),
        question=row["question"],
        answer={"type": "model_ref"},
        expected_refs=row.get("expected_refs", []),
        trajectory={"expected_tools": row.get("expected_tools", []), "ordered": ordered(row.get("expected_tools", []))},
        requires_assumptions=row.get("requires_assumptions", False),
        review=review(row),
        provenance=provenance(file, row, commit),
    ) for row in read_jsonl(repo / GOLD_DIR / file)]


def investigate(repo: Path, commit: str) -> list[dict]:
    file = "investigate-gold.jsonl"
    return [task(
        id=f"investigate-{row['id']}",
        mode="investigate",
        category=row["category"],
        split=row["split"],
        as_of=row.get("as_of"),
        companies=companies(row),
        question=row["question"],
        answer={"type": "composite", "tolerance": row.get("tolerance", 0.005)},
        required_points=row.get("required_points", []),
        expected_gaps=row.get("expected_gaps", []),
        parts=[{"mode": p["mode"], "values": p.get("expected_answer", []), "expected_refs": p.get("expected_refs", []), "chunk_ids": []}
               for p in row.get("parts", [])],
        requires_assumptions=row.get("requires_assumptions", False),
        review=review(row),
        provenance=provenance(file, row, commit),
    ) for row in read_jsonl(repo / GOLD_DIR / file)]


def extraction(repo: Path, commit: str) -> list[dict]:
    file = "extraction-gold.jsonl"
    out = []
    for row in read_jsonl(repo / GOLD_DIR / file):
        period = row.get("target_period") or row["period"]
        out.append(task(
            id=f"extract-{row['id']}",
            mode="extraction",
            layers=["extraction"],
            category=row["metric"],
            kind=row.get("segment"),
            split="test",
            companies=[row["ticker"]],
            answer={"type": "number", "tolerance": 0.0,
                    "values": [{"value": row["value"], "unit": row["unit"], "company": row["ticker"], "period": period}]},
            trajectory={},
            evidence={"gold": [{"company": row["ticker"], "period": row["period"], "form": "ER", "evidence": row["quote"],
                                "block": row.get("block"), "source": row["source"]}]},
            review={"origin": "agent-repo:crosscheck", "verified_by": row.get("verified_by")},
            provenance=provenance(file, row, commit),
        ))
    return out


def imported_tasks(repo: Path, commit: str) -> list[dict]:
    return ask(repo, commit) + research(repo, commit) + investigate(repo, commit) + extraction(repo, commit)
