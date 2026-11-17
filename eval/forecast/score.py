import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import median

from scipy.stats import wilcoxon
from statsmodels.stats.proportion import proportion_confint

sys.path.insert(0, str(Path(__file__).resolve().parent))
from consensus import load  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results" / "forecast"
SAME_BASIS = 0.05
LARGE_MISS = 0.10


def ape(forecast: float | None, actual: float) -> float | None:
    return None if forecast is None or not actual else abs(forecast - actual) / abs(actual)


def rounded(value, digits=4):
    return None if value is None else round(value, digits)


def accuracy(rows: list[dict]) -> dict:
    out = {}
    for group in ("revenue", "main_kpi", "eps_diluted"):
        chosen = [r for r in rows if r["group"] == group]
        model = [r["model_ape"] for r in chosen if r["model_ape"] is not None]
        paired = [(r["model_ape"], r["naive_ape"]) for r in chosen
                  if r["model_ape"] is not None and r["naive_ape"] is not None]
        beats = sum(m < n for m, n in paired)
        out[group] = {"forecasts": len(model),
                      "model_mdape": rounded(median(model)) if model else None,
                      "naive_mdape": rounded(median(n for _, n in paired)) if paired else None,
                      "beats_naive": beats, "paired": len(paired),
                      "beats_naive_ci95": [rounded(x, 3) for x in proportion_confint(beats, len(paired), method="wilson")] if paired else None,
                      "wilcoxon_p": rounded(wilcoxon([m for m, _ in paired], [n for _, n in paired]).pvalue, 3) if len(paired) > 5 else None}
    return out


def quadrant(model_ape: float, consensus_ape: float) -> str:
    model_large, consensus_large = model_ape > LARGE_MISS, consensus_ape > LARGE_MISS
    if model_large and consensus_large:
        return "both_missed"
    if model_large:
        return "agent_missed"
    if consensus_large:
        return "agent_beat_street"
    return "both_close"


def versus_consensus(eps_rows: list[dict]) -> tuple[dict, list[dict]]:
    rows = []
    for r in eps_rows:
        street = load(r["ticker"]).get(r["target"])
        if not street or street["consensus_eps"] is None:
            continue
        actual = float(r["actual"])
        same_basis = street["reported_eps"] is not None and ape(street["reported_eps"], actual) is not None \
            and ape(street["reported_eps"], actual) <= SAME_BASIS
        leak_safe = street["reported_date"] is None or r["as_of"] <= street["reported_date"]
        if not leak_safe:
            raise RuntimeError(f"{r['ticker']} {r['target']}: forecast as of {r['as_of']} is after the print")
        model_ape, consensus_ape = r["model_ape"], ape(street["consensus_eps"], actual)
        rows.append({"ticker": r["ticker"], "target": r["target"], "as_of": r["as_of"],
                     "reported_date": street["reported_date"], "actual_gaap": actual,
                     "av_reported": street["reported_eps"], "same_basis": same_basis,
                     "agent": rounded(float(r["forecast"])), "consensus": street["consensus_eps"],
                     "agent_ape": rounded(model_ape), "consensus_ape": rounded(consensus_ape),
                     "agent_closer": abs(float(r["forecast"]) - actual) < abs(street["consensus_eps"] - actual),
                     "quadrant": quadrant(model_ape, consensus_ape)})
    matched = [r for r in rows if r["same_basis"]]
    wins = sum(r["agent_closer"] for r in matched)
    summary = {"quarters": len(rows), "same_basis": len(matched), "excluded_basis_mismatch": len(rows) - len(matched),
               "agent_closer": wins,
               "agent_closer_rate": rounded(wins / len(matched), 3) if matched else None,
               "agent_closer_ci95": [rounded(x, 3) for x in proportion_confint(wins, len(matched), method="wilson")] if matched else None,
               "agent_mdape": rounded(median(r["agent_ape"] for r in matched)) if matched else None,
               "consensus_mdape": rounded(median(r["consensus_ape"] for r in matched)) if matched else None,
               "wilcoxon_p": rounded(wilcoxon([r["agent_ape"] for r in matched], [r["consensus_ape"] for r in matched]).pvalue, 3) if len(matched) > 5 else None,
               "quadrants": {q: sum(r["quadrant"] == q for r in matched)
                             for q in ("both_close", "agent_beat_street", "agent_missed", "both_missed")}}
    return summary, rows


def pct(value):
    return "–" if value is None else f"{value * 100:.1f}%"


def report(label: str, acc: dict, street: dict, rows: list[dict]) -> str:
    lines = [f"# Forecast accuracy: {label}", "",
             "Walk-forward: each forecast is made the day after a release, for the next quarter, with the agent's "
             "leakage probe on. Errors are absolute % errors against the first-reported SEC value.", "",
             "## Against actuals", "",
             "| Metric | Forecasts | Agent MdAPE | Naive MdAPE | Agent beats naive | 95% CI | Wilcoxon p |",
             "|---|---|---|---|---|---|---|"]
    for group, a in acc.items():
        ci = a["beats_naive_ci95"]
        lines.append(f"| {group} | {a['forecasts']} | {pct(a['model_mdape'])} | {pct(a['naive_mdape'])} | "
                     f"{a['beats_naive']}/{a['paired']} | {pct(ci[0]) + '–' + pct(ci[1]) if ci else '–'} | {a['wilcoxon_p'] or '–'} |")
    ci = street["agent_closer_ci95"] or [None, None]
    lines += ["", "## EPS against consensus (Alpha Vantage)", "",
              f"Scored on the same GAAP actual. {street['same_basis']} of {street['quarters']} quarters have a matching "
              f"basis (Alpha Vantage's reported EPS within {SAME_BASIS:.0%} of SEC GAAP diluted EPS); "
              f"{street['excluded_basis_mismatch']} are excluded (adjusted vs GAAP, or split-adjusted).", "",
              f"- Agent closer than consensus: **{street['agent_closer']}/{street['same_basis']}** "
              f"({pct(street['agent_closer_rate'])}, 95% CI {pct(ci[0])}–{pct(ci[1])})",
              f"- MdAPE: agent {pct(street['agent_mdape'])}, consensus {pct(street['consensus_mdape'])} "
              f"(Wilcoxon p {street['wilcoxon_p'] or '–'})", "",
              f"| Quadrant (large miss > {LARGE_MISS:.0%}) | Quarters | Meaning |", "|---|---|---|",
              f"| both_close | {street['quadrants']['both_close']} | Normal quarter |",
              f"| agent_beat_street | {street['quadrants']['agent_beat_street']} | Agent right, Street wrong |",
              f"| agent_missed | {street['quadrants']['agent_missed']} | Agent's own error: investigate |",
              f"| both_missed | {street['quadrants']['both_missed']} | Genuine surprise |", "",
              "| Ticker | Quarter | GAAP actual | Agent | Consensus | Agent APE | Consensus APE | Quadrant |",
              "|---|---|---|---|---|---|---|---|"]
    for r in sorted((r for r in rows if r["same_basis"]), key=lambda r: (r["ticker"], r["target"])):
        lines.append(f"| {r['ticker']} | {r['target']} | {r['actual_gaap']} | {r['agent']:.2f} | {r['consensus']} | "
                     f"{pct(r['agent_ape'])} | {pct(r['consensus_ape'])} | {r['quadrant']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="defaults")
    args = ap.parse_args()
    out = RESULTS / args.label
    rows = []
    for r in csv.DictReader((out / "forecasts.csv").open()):
        actual = float(r["actual"])
        forecast = float(r["forecast"]) if r["forecast"] else None
        naive = float(r["seasonal_naive"]) if r["seasonal_naive"] else None
        group = "revenue" if r["metric"] == "revenue" else "eps_diluted" if r["metric"] == "eps_diluted" else "main_kpi"
        rows.append(r | {"group": group, "model_ape": ape(forecast, actual), "naive_ape": ape(naive, actual)})
    acc = accuracy(rows)
    street, street_rows = versus_consensus([r for r in rows if r["group"] == "eps_diluted" and r["model_ape"] is not None])
    (out / "summary.json").write_text(json.dumps({"accuracy": acc, "consensus": street}, indent=2))
    with (out / "consensus.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(street_rows[0]))
        writer.writeheader()
        writer.writerows(street_rows)
    (out / "report.md").write_text(report(args.label, acc, street, street_rows))
    print(json.dumps({"accuracy": acc, "consensus": street}, indent=1))


if __name__ == "__main__":
    main()
