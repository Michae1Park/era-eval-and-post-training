import argparse
import csv
import os
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT = (ROOT / ".." / "equity-research-agent").resolve()
RESULTS = ROOT / "results" / "forecast"
EXTRA_METRICS = [("eps_diluted", "eps_diluted")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*")
    ap.add_argument("--label", default="defaults")
    ap.add_argument("--proposer", choices=("defaults", "llm"), default="defaults")
    args = ap.parse_args()
    os.environ.setdefault("ERA_COMPANIES", str(AGENT / "companies.yaml"))
    os.chdir(AGENT)
    from era_agent.evaluation import backtest as agent_backtest
    from era_agent.research.forecast import knobs
    from era_agent.research.model.history import TEMPLATE_OF

    base_metrics = agent_backtest.metrics_for
    agent_backtest.metrics_for = lambda ticker: base_metrics(ticker) + EXTRA_METRICS
    settings = knobs()
    settings["proposer"]["method"] = args.proposer
    search = None
    if args.proposer == "llm":
        import yaml
        from era_agent.asof import AsOf
        from era_agent.retrieval.search import SubQuestionRetriever
        from era_agent.store import Store

        retrieval = yaml.safe_load((AGENT / "experiments/v1/config.yaml").read_text())["retrieval"]
        search = SubQuestionRetriever.from_settings(Store(agent_backtest.ROOT / "data/v4/build/parent_child.db", AsOf.today()), retrieval)
    db = AGENT / "data/v4/build/parent_child.db"
    rows = []
    for ticker in args.tickers or sorted(TEMPLATE_OF):
        found = agent_backtest.backtest(db, ticker, settings, search)
        print(f"{ticker}: {len(found)} rows")
        rows += found
    out = RESULTS / args.label
    out.mkdir(parents=True, exist_ok=True)
    with (out / "forecasts.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0])))
        writer.writeheader()
        writer.writerows(asdict(r) for r in rows)
    print(f"wrote {out / 'forecasts.csv'}")


if __name__ == "__main__":
    main()
