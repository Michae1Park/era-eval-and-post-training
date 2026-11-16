import argparse
import html
import json
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

from schema import stable_fraction

BENCH_DIR = Path(__file__).parent.parent
MODE_ORDER = ["ask", "investigate", "research", "multi_turn", "report", "extraction"]
MODE_TITLES = {
    "ask": "Ask: factual questions",
    "investigate": "Investigate: multi-step questions",
    "research": "Research: model questions",
    "multi_turn": "Multi-turn conversations",
    "report": "Report: earnings notes",
    "extraction": "Extraction: KPI labels (component)",
}
TRAIN_SAMPLE = 40
CSS = """
@page { size: A4; margin: 14mm 12mm; }
body { font: 9.5pt/1.4 -apple-system, 'Segoe UI', Roboto, sans-serif; color: #1a1a1a; }
h1 { font-size: 20pt; margin: 0 0 4px; } h2 { font-size: 14pt; margin: 22px 0 6px; border-bottom: 2px solid #333; page-break-before: always; }
h3 { font-size: 11pt; margin: 14px 0 4px; color: #333; }
.meta { color: #666; font-size: 8.5pt; }
.card { border: 1px solid #ccc; border-radius: 4px; padding: 6px 8px; margin: 6px 0; page-break-inside: avoid; }
.head { display: flex; justify-content: space-between; gap: 8px; }
.id { font-family: ui-monospace, Menlo, monospace; font-size: 8.5pt; font-weight: 600; }
.badges span { display: inline-block; font-size: 7.5pt; padding: 0 5px; border-radius: 3px; margin-left: 3px; background: #eee; }
.badges .test { background: #fde2e2; } .badges .dev { background: #e2f0fd; } .badges .train { background: #e8f5e2; }
.badges .unverified { background: #fff3cd; } .badges .verified { background: #d4edda; }
.q { font-weight: 600; margin: 3px 0; }
table { border-collapse: collapse; width: 100%; font-size: 8.5pt; margin: 3px 0; }
td, th { border: 1px solid #ddd; padding: 2px 4px; text-align: left; vertical-align: top; }
th { background: #f5f5f5; }
.k { color: #555; width: 110px; }
code, .mono { font-family: ui-monospace, Menlo, monospace; font-size: 7.8pt; word-break: break-all; }
.quote { color: #444; font-style: italic; }
.box { display: inline-block; width: 10px; height: 10px; border: 1px solid #555; margin-right: 4px; vertical-align: middle; }
.review { margin-top: 4px; font-size: 8pt; color: #555; }
.inject { background: #fff0f0; border-left: 3px solid #c00; padding: 2px 6px; }
"""


def esc(x) -> str:
    return html.escape(str(x)) if x is not None else ""


def fmt_value(v) -> str:
    if not isinstance(v, dict):
        return esc(v)
    parts = [f"<b>{esc(v.get('value'))}</b> {esc(v.get('unit', ''))}"]
    extra = " · ".join(esc(v[k]) for k in ("company", "period", "label") if v.get(k) and not str(v.get(k)).startswith(("kpi:", "guide:", "xbrl:")))
    if extra:
        parts.append(f"<span class='meta'>({extra})</span>")
    return " ".join(parts)


def row(label: str, content: str) -> str:
    return f"<tr><td class='k'>{esc(label)}</td><td>{content}</td></tr>" if content else ""


def bullet(items) -> str:
    return "<br>".join(f"• {esc(i)}" for i in items) if items else ""


def trajectory_text(t: dict) -> str:
    traj = t.get("trajectory") or {}
    steps = []
    for step in traj.get("ordered", []):
        args = step.get("args") or {}
        detail = ", ".join(f"{k}={v}" for k, v in args.items())
        if step.get("periods"):
            detail += (", " if detail else "") + "periods=" + "/".join(step["periods"])
        steps.append(f"{esc(step['tool'])}({esc(detail)})")
    text = " → ".join(steps)
    if traj.get("forbidden_tools"):
        text += f"<br><span class='meta'>forbidden: {esc(', '.join(traj['forbidden_tools']))}</span>"
    return text


def evidence_text(t: dict) -> str:
    out = []
    for g in t["evidence"].get("gold", [])[:4]:
        where = " ".join(esc(g.get(k)) for k in ("company", "period", "form") if g.get(k))
        out.append(f"<span class='meta'>{where}</span> <span class='quote'>{esc(str(g.get('evidence', ''))[:220])}</span>")
    if t["evidence"].get("chunk_ids"):
        out.append("<span class='meta'>chunks:</span> <span class='mono'>" + esc(", ".join(t["evidence"]["chunk_ids"][:6])) + "</span>")
    if t["evidence"].get("fact_ids"):
        out.append("<span class='meta'>XBRL:</span> <span class='mono'>" + esc(", ".join(t["evidence"]["fact_ids"][:3])) + "</span>")
    return "<br>".join(out)


def card(t: dict) -> str:
    verified = t["review"].get("verified_by")
    status = f"<span class='verified'>verified {esc(verified)}</span>" if verified else "<span class='unverified'>unverified</span>"
    badges = (f"<span class='{t['split']}'>{t['split']}</span><span>{esc(t['category'])}</span>"
              + (f"<span>{esc(t['kind'])}</span>" if t.get("kind") else "")
              + "".join(f"<span>{esc(tag)}</span>" for tag in t.get("tags", [])) + status)
    body = []
    if t.get("question"):
        body.append(f"<div class='q'>{esc(t['question'])}</div>")
    rows = [row("as of", esc(t.get("as_of"))), row("companies", esc(", ".join(t["companies"])))]
    answer = t["answer"]
    if answer.get("should_abstain"):
        rows.append(row("expected", f"<b>Decline</b> ({esc(t.get('failure_mode') or 'should abstain')})"))
    elif answer.get("values"):
        rows.append(row(f"gold ({answer.get('type')}, tol {answer.get('tolerance')})", "<br>".join(fmt_value(v) for v in answer["values"])))
    elif answer.get("type"):
        rows.append(row("answer type", esc(answer["type"])))
    rows.append(row("required points", bullet(t.get("required_points"))))
    rows.append(row("expected gaps", bullet(t.get("expected_gaps"))))
    rows.append(row("model refs", "<span class='mono'>" + esc(", ".join(t.get("expected_refs", []))) + "</span>" if t.get("expected_refs") else ""))
    for i, p in enumerate(t.get("parts", []), 1):
        content = "<br>".join(fmt_value(v) for v in p.get("values", []))
        if p.get("expected_refs"):
            content += "<br><span class='mono'>refs: " + esc(", ".join(p["expected_refs"])) + "</span>"
        rows.append(row(f"part {i} ({p['mode']})", content or "<span class='meta'>text only</span>"))
    for turn in t.get("turns", []):
        content = f"<b>{esc(turn['question'])}</b>"
        if turn.get("resolves_to"):
            content += f"<br><span class='meta'>means: {esc(turn['resolves_to'])}</span>"
        if turn.get("values"):
            content += "<br>" + "<br>".join(fmt_value(v) for v in turn["values"])
        if turn.get("required_points"):
            content += "<br>" + bullet(turn["required_points"])
        if turn.get("expected_refs"):
            content += "<br><span class='mono'>refs: " + esc(", ".join(turn["expected_refs"])) + "</span>"
        if (turn.get("answer") or {}).get("should_abstain"):
            content += "<br><b>Decline</b>"
        rows.append(row(f"turn {turn['turn']}", content))
    if t.get("report"):
        r = t["report"]
        rows.append(row("report checks", bullet(r.get("checks"))))
        rows.append(row("must include", "<br>".join(fmt_value(v) for v in r.get("required_values", []))))
    if t.get("injection"):
        inj = t["injection"]
        rows.append(row("injection", f"<div class='inject'>into <b>{esc(inj['tool'])}</b> ({esc(inj['position'])}): "
                                     f"“{esc(inj['payload'])}”<br>fail if answer contains: <code>{esc(inj['canary'])}</code></div>"))
    rows.append(row("trajectory", trajectory_text(t)))
    rows.append(row("evidence", evidence_text(t)))
    body.append("<table>" + "".join(r for r in rows if r) + "</table>")
    body.append("<div class='review'><span class='box'></span>correct <span class='box'></span>fix needed "
                "<span class='box'></span>drop &nbsp; notes: ______________________________</div>")
    return (f"<div class='card'><div class='head'><span class='id'>{esc(t['id'])}</span><span class='badges'>{badges}</span></div>"
            + "".join(body) + "</div>")


def extraction_table(tasks: list[dict]) -> str:
    rows = ["<tr><th>✓</th><th>id</th><th>value</th><th>quote</th></tr>"]
    for t in tasks:
        v = t["answer"]["values"][0]
        quote = t["evidence"]["gold"][0].get("evidence", "") if t["evidence"]["gold"] else ""
        rows.append(f"<tr><td><span class='box'></span></td><td class='mono'>{esc(t['id'][8:])}</td>"
                    f"<td>{esc(v['value'])} {esc(v['unit'])}</td><td class='quote'>{esc(quote[:160])}</td></tr>")
    return "<table>" + "".join(rows) + "</table>"


def render_html(tasks: list[dict], manifest: dict, coverage_md: str) -> str:
    evals = [t for t in tasks if t["split"] in ("dev", "test")]
    train = [t for t in tasks if t["split"] == "train"]
    by_mode = defaultdict(lambda: defaultdict(list))
    for t in evals:
        by_mode[t["mode"]][t["category"]].append(t)

    parts = [f"<h1>ERA-Bench v{esc(manifest['version'])}: review copy</h1>",
             f"<div class='meta'>Agent commit {esc(manifest['agent_commit'])} · {manifest['tasks']} tasks "
             f"({esc(json.dumps(manifest['splits']))}) · hash {esc(manifest['sha256_16'])}</div>",
             "<h3>How to review</h3><p>Each card shows the question, the gold answer and where it came from. Tick <b>correct</b>, "
             "<b>fix needed</b> or <b>drop</b>. Verified ids go into <code>bench/review/verified.tsv</code> "
             "(id, reviewer, date); the next build marks them verified.</p>",
             "<h3>Contents</h3><ul>"]
    for mode in MODE_ORDER:
        if mode in by_mode:
            n = sum(len(v) for v in by_mode[mode].values())
            parts.append(f"<li>{esc(MODE_TITLES[mode])}: {n} tasks</li>")
    parts.append(f"<li>Train split: {len(train)} tasks ({TRAIN_SAMPLE} sampled here)</li></ul>")
    parts.append("<h3>Coverage</h3><pre class='mono' style='white-space:pre-wrap'>" + esc(coverage_md.split("## Categories")[0]) + "</pre>")

    for mode in MODE_ORDER:
        if mode not in by_mode:
            continue
        parts.append(f"<h2>{esc(MODE_TITLES[mode])}</h2>")
        for category in sorted(by_mode[mode]):
            group = sorted(by_mode[mode][category], key=lambda t: (t["split"], t["id"]))
            parts.append(f"<h3>{esc(category)} ({len(group)})</h3>")
            parts.append(extraction_table(group) if mode == "extraction" else "".join(card(t) for t in group))

    sample = sorted(train, key=lambda t: stable_fraction(t["id"]))[:TRAIN_SAMPLE]
    parts.append(f"<h2>Train split sample ({TRAIN_SAMPLE} of {len(train)})</h2>")
    parts.append("".join(card(t) for t in sorted(sample, key=lambda t: t["id"])))
    return f"<!doctype html><html><head><meta charset='utf-8'><title>ERA-Bench review</title><style>{CSS}</style></head><body>{''.join(parts)}</body></html>"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=BENCH_DIR / "review" / "era-bench-review.pdf")
    parser.add_argument("--chrome", default="google-chrome")
    args = parser.parse_args()

    tasks = [json.loads(line) for split in ("dev", "test", "train")
             for line in (BENCH_DIR / "tasks" / f"{split}.jsonl").read_text().splitlines() if line.strip()]
    manifest = json.loads((BENCH_DIR / "manifest.json").read_text())
    document = render_html(tasks, manifest, (BENCH_DIR / "COVERAGE.md").read_text())

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "review.html"
        page.write_text(document)
        subprocess.run([args.chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={args.out.resolve()}", page.as_uri()], check=True, capture_output=True)
    print(args.out)


if __name__ == "__main__":
    main()
