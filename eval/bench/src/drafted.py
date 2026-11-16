from pathlib import Path

import yaml

from data import AgentData
from schema import task

DRAFTED_DIR = Path(__file__).parent.parent / "drafted"
TOP_LEVEL = {"mode", "layers", "category", "kind", "as_of", "companies", "question", "required_points", "expected_gaps",
             "requires_assumptions", "failure_mode", "injection", "tags"}


class UnresolvedRef(ValueError):
    pass


def resolve_ref(data: AgentData, ref: str) -> dict:
    kind, ticker, *rest = ref.split(":")
    if kind == "kpi":
        metric, *segment, period = rest
        k = data.kpi(ticker, metric, period, segment[0] if segment else None)
        if not k and not segment:
            k = data.kpi(ticker, metric, period, "total")
        if not k:
            raise UnresolvedRef(ref)
        return {"value": k.value, "unit": k.unit, "company": ticker, "period": period, "label": ref,
                "_evidence": {"company": ticker, "period": period, "form": "ER", "evidence": k.quote, "block": k.block}}
    if kind == "guide":
        metric, bound, target = rest
        for k in data.kpis:
            if k.ticker == ticker and k.metric == f"guide.{metric}.{bound}" and k.target_period == target:
                return {"value": k.value, "unit": k.unit, "company": ticker, "period": target, "label": ref,
                        "_evidence": {"company": ticker, "period": k.period, "form": "ER", "evidence": k.quote, "block": k.block}}
        raise UnresolvedRef(ref)
    if kind == "xbrl":
        metric, period = rest
        span = "year" if period.startswith("FY") else "quarter"
        f = data.facts(ticker, metric, span).get(period)
        if not f:
            raise UnresolvedRef(ref)
        return {"value": f.display_value, "unit": f.display_unit, "company": ticker, "period": period, "label": ref, "_fact": f.fact_id}
    raise UnresolvedRef(ref)


def operand(data: AgentData, item, evidence: list, facts: list) -> float:
    if isinstance(item, (int, float)):
        return float(item)
    resolved = resolve_ref(data, item)
    collect(resolved, evidence, facts)
    return resolved["value"]


def collect(resolved: dict, evidence: list, facts: list) -> None:
    if "_evidence" in resolved:
        evidence.append(resolved.pop("_evidence"))
    if "_fact" in resolved:
        facts.append(resolved.pop("_fact"))


def resolve_value(data: AgentData, spec: dict, evidence: list, facts: list) -> dict:
    if "ref" in spec:
        resolved = resolve_ref(data, spec["ref"])
        collect(resolved, evidence, facts)
        if spec.get("label"):
            resolved["label"] = spec["label"]
        return resolved
    if "compute" in spec:
        (op, (a, b)), = spec["compute"].items()
        x, y = operand(data, a, evidence, facts), operand(data, b, evidence, facts)
        result = {"growth": lambda: (x / y - 1) * 100, "ratio": lambda: x / y * 100, "ratio_of_value": lambda: x / y * 100,
                  "per_unit": lambda: x / y, "diff": lambda: x - y}[op]()
        return {"value": round(result, 2), "unit": spec.get("unit"), "label": spec.get("label", f"{op}({a}, {b})")}
    return {k: v for k, v in spec.items()}


def resolve_values(data: AgentData, specs: list, evidence: list, facts: list) -> list[dict]:
    return [resolve_value(data, s, evidence, facts) for s in specs or []]


def known_chunks(data: AgentData, ids: list[str]) -> list[str]:
    missing = [i for i in ids if not data.db.execute("select 1 from children where id=?", (i,)).fetchone()]
    if missing:
        raise UnresolvedRef(f"chunks {missing}")
    return ids


def build_task(data: AgentData, raw: dict, defaults: dict, source: str) -> dict:
    spec = {**defaults, **raw}
    evidence, facts, chunk_ids = [], [], list(spec.get("evidence_chunks", []))
    answer = dict(spec.get("answer", {}))
    answer["values"] = resolve_values(data, answer.get("values"), evidence, facts)

    parts = []
    for part in spec.get("parts", []):
        chunk_ids += part.get("chunk_ids", [])
        parts.append({"mode": part["mode"], "values": resolve_values(data, part.get("values"), evidence, facts),
                      "expected_refs": part.get("expected_refs", []), "chunk_ids": part.get("chunk_ids", [])})

    turns = []
    for number, turn in enumerate(spec.get("turns", []), start=1):
        chunk_ids += turn.get("chunk_ids", [])
        turns.append({"turn": number, "question": turn["question"], "resolves_to": turn.get("resolves_to"),
                      "values": resolve_values(data, turn.get("values"), evidence, facts),
                      "answer": turn.get("answer"), "required_points": turn.get("required_points", []),
                      "expected_refs": turn.get("expected_refs", []), "expected_tools": turn.get("expected_tools", []),
                      "chunk_ids": turn.get("chunk_ids", [])})

    report = None
    if spec.get("mode") == "report":
        report = {**spec["report"], "required_values": resolve_values(data, [{"ref": r} for r in spec["required_values"]], evidence, facts)}

    expected_tools = spec.get("expected_tools", [])
    return task(
        id=spec["id"],
        **{k: spec[k] for k in TOP_LEVEL if k in spec},
        answer=answer,
        parts=parts,
        turns=turns,
        report=report,
        trajectory={"expected_tools": expected_tools,
                    "ordered": [{"tool": t} for t in expected_tools],
                    "forbidden_tools": spec.get("forbidden_tools", [])},
        evidence={"gold": evidence, "chunk_ids": known_chunks(data, chunk_ids), "fact_ids": facts},
        review={"origin": "drafted:claude", "verified_by": None},
        provenance={"file": f"bench/drafted/{source}"},
    )


def drafted_tasks(data: AgentData) -> tuple[list[dict], list[str]]:
    tasks, errors = [], []
    for path in sorted(DRAFTED_DIR.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text())
        for raw in doc["tasks"]:
            try:
                tasks.append(build_task(data, raw, doc.get("defaults", {}), path.name))
            except UnresolvedRef as e:
                errors.append(f"{path.name}:{raw['id']}: unresolved {e}")
    return tasks, errors
