import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
GPU_HOURLY_USD = 0.86
WORKERS = 4


def read(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def pct(v):
    return "–" if v is None else f"{v * 100:.1f}%"


def ci(pair):
    return "–" if not pair or None in pair else f"{pct(pair[0])}–{pct(pair[1])}"


def runs() -> list[tuple[str, dict]]:
    out = []
    for path in sorted(RESULTS.glob("*/dev/summary.json")):
        label = path.parent.parent.name
        if label not in ("forecast",):
            out.append((label, read(path)))
    return out


def pass_k(overall: dict) -> str:
    key = next((k for k in overall if k.startswith("pass^")), None)
    return f"{overall[key] * 100:.1f}% ({key})" if key else "–"


def section_runs(lines: list[str]) -> None:
    lines += ["## End-to-end runs (dev)", "",
              "| Run | Tasks | pass@1 | 95% CI | pass^k | Judged pass | Grounded | Points covered | Mean s | Tokens in/out | $ / task |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for label, s in runs():
        o = s["overall"].get("all") or {}
        j = s.get("judged") or {}
        cost = s["seconds_mean"] / WORKERS * GPU_HOURLY_USD / 3600
        lines.append(f"| {label} | {o.get('tasks', '–')} | {pct(o.get('pass@1'))} | {ci(o.get('ci95'))} | {pass_k(o)} | "
                     f"{pct(j.get('pass_rate'))} | {pct(j.get('grounded_rate'))} | {pct(j.get('points_covered_rate'))} | "
                     f"{s['seconds_mean']} | {s['tokens_mean']['input']}/{s['tokens_mean']['output']} | {cost:.4f} |")
    lines += ["", f"Cost assumes one L40S at ${GPU_HOURLY_USD}/h shared by {WORKERS} concurrent tasks.", ""]
    base = read(RESULTS / "baseline-27b" / "dev" / "summary.json")
    if base:
        lines += ["### Baseline by mode", "", "| Mode | Tasks | pass@1 | 95% CI | pass^k |", "|---|---|---|---|---|"]
        for mode, o in base["by_mode"].items():
            lines.append(f"| {mode} | {o['tasks']} | {pct(o['pass@1'])} | {ci(o['ci95'])} | {pass_k(o)} |")
        lines.append("")


def section_compare(lines: list[str]) -> None:
    rows = []
    for path in sorted(RESULTS.glob("*/dev/compare-baseline-27b.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        o = data.get("overall") or {}
        rows.append(f"| {path.parent.parent.name} | {o.get('tasks', '–')} | {pct(o.get('delta'))} | {ci(o.get('delta_ci95'))} | "
                    f"{o.get('mcnemar_p', '–')} |")
    if rows:
        lines += ["## Paired vs. baseline-27b (shared tasks)", "", "| Run | Tasks | Δ pass@1 | 95% CI | McNemar p |",
                  "|---|---|---|---|---|"] + rows + [""]


def section_taxonomy(lines: list[str]) -> None:
    lines += ["## Failure taxonomy", "", "| Run | Failed | Top codes (share of scored) | Root layer |", "|---|---|---|---|"]
    for path in sorted(RESULTS.glob("*/dev/taxonomy.json")):
        t = read(path)
        top = ", ".join(f"{c} {v['rate_of_scored'] * 100:.0f}%" for c, v in list(t["codes"].items())[:4])
        roots = ", ".join(f"{k} {v}" for k, v in t["root_layer"].items())
        lines.append(f"| {path.parent.parent.name} | {t['failed']}/{t['scored']} | {top} | {roots} |")
    lines.append("")


def section_layers(lines: list[str]) -> None:
    r = read(RESULTS / "retrieval-baseline" / "dev" / "retrieval-summary.json")
    if r:
        lines += ["## L1 retrieval (dev, gold = earnings-release chunks)", "", "| Metric | Mean | 95% CI |", "|---|---|---|"]
        lines += [f"| {k} | {v['mean']:.3f} | {v['ci95'][0]}–{v['ci95'][1]} |" for k, v in r["overall"].items()] + [""]
    gens = [(p.parent.parent.name, read(p)) for p in sorted(RESULTS.glob("*/dev/generation-summary.json"))]
    if gens:
        lines += ["## L2 generation with gold context", "", "| Model run | Tasks | Pass |", "|---|---|---|"]
        lines += [f"| {label} | {g['tasks']} | {pct(g['pass_rate_gold_context'])} |" for label, g in gens] + [""]


def section_judges(lines: list[str]) -> None:
    a = read(RESULTS / "baseline-27b" / "dev" / "judge-agreement.json")
    if not a:
        return
    lines += ["## Judges (RQ1)", "", "| Dimension | Krippendorff α (panel) |", "|---|---|"]
    lines += [f"| {d} | {v if v is not None else '–'} |" for d, v in a["krippendorff_alpha"].items()]
    lines += ["", "| Pair | covered κ | grounded κ | safe κ |", "|---|---|---|---|"]
    for pair, dims in a["judge_vs_judge"].items():
        lines.append(f"| {pair} | " + " | ".join(str(dims[d]["value"]) for d in ("covered", "grounded", "safe")) + " |")
    if "judge_vs_human" in a:
        lines += ["", "| Judge vs. human | covered κ | grounded κ | safe κ |", "|---|---|---|---|"]
        for name, dims in a["judge_vs_human"].items():
            lines.append(f"| {name} | " + " | ".join(str(dims[d]["value"]) for d in ("covered", "grounded", "safe")) + " |")
    else:
        lines += ["", "Judge vs. human: pending human labels (`eval/judge/human.jsonl`)."]
    lines += ["", f"Verbosity bias (Spearman length vs. tone): {a['verbosity_bias']['spearman_length_tone']} (n={a['verbosity_bias']['n']})"]
    if "self_preference" in a:
        sp = a["self_preference"]
        lines.append(f"Self-preference: {sp['probe']} positive rate {pct(sp['probe_positive_rate'])} vs. panel "
                     + ", ".join(f"{k} {pct(v)}" for k, v in sp["panel_positive_rate"].items()))
    lines.append("")


def section_forecast(lines: list[str]) -> None:
    rows = []
    for path in sorted((RESULTS / "forecast").glob("*/summary.json")):
        s = read(path)
        for metric, a in s["accuracy"].items():
            rows.append(f"| {path.parent.name} | {metric} | {a['forecasts']} | {pct(a['model_mdape'])} | {pct(a['naive_mdape'])} | "
                        f"{a['beats_naive']}/{a['paired']} | {a['wilcoxon_p']} |")
        c = s["consensus"]
        rows.append(f"| {path.parent.name} | EPS vs. consensus | {c['same_basis']} | {pct(c['agent_mdape'])} | {pct(c['consensus_mdape'])} (consensus) | "
                    f"{c['agent_closer']}/{c['same_basis']} closer | {c['wilcoxon_p']} |")
    if rows:
        lines += ["## L5 forecast accuracy", "", "| Proposer | Metric | n | Agent MdAPE | Baseline MdAPE | Agent wins | Wilcoxon p |",
                  "|---|---|---|---|---|---|---|"] + rows + [""]


def main() -> None:
    lines = ["# Baseline evaluation report", "", "Generated by `eval/report.py`; source files under `results/`.", ""]
    for section in (section_runs, section_compare, section_taxonomy, section_layers, section_judges, section_forecast):
        section(lines)
    (RESULTS / "report.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {RESULTS / 'report.md'}")


if __name__ == "__main__":
    main()
