import hashlib
import json

SUITE = "marketplaces"
TASK_FIELDS = {
    "id": None,
    "suite": SUITE,
    "mode": "ask",
    "layers": ["e2e", "trajectory"],
    "category": None,
    "kind": None,
    "split": None,
    "tags": [],
    "as_of": None,
    "companies": [],
    "question": None,
    "turns": [],
    "answer": {"type": None, "values": [], "tolerance": 0.005, "should_abstain": False},
    "required_points": [],
    "expected_gaps": [],
    "expected_refs": [],
    "trajectory": {"expected_tools": [], "ordered": [], "forbidden_tools": []},
    "evidence": {"gold": [], "acceptable": [], "chunk_ids": [], "fact_ids": []},
    "parts": [],
    "injection": None,
    "report": None,
    "requires_assumptions": False,
    "failure_mode": None,
    "review": {"origin": None, "verified_by": None, "verified_on": None},
    "provenance": {},
}


def task(**fields) -> dict:
    unknown = set(fields) - set(TASK_FIELDS)
    if unknown:
        raise ValueError(f"unknown task fields: {sorted(unknown)}")
    built = json.loads(json.dumps(TASK_FIELDS))
    for key, value in fields.items():
        if isinstance(built[key], dict) and isinstance(value, dict):
            built[key].update(value)
        else:
            built[key] = value
    return built


def stable_fraction(text: str) -> float:
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def pick(options: list, key: str):
    return options[int(stable_fraction(key) * len(options)) % len(options)]


def value(v: float, unit: str, company: str | None = None, label: str | None = None, period: str | None = None) -> dict:
    out = {"value": v, "unit": unit}
    if company:
        out["company"] = company
    if label:
        out["label"] = label
    if period:
        out["period"] = period
    return out
