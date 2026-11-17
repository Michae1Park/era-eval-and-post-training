import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "eval" / "forecast" / "consensus"
TICKERS = ["ABNB", "BKNG", "CART", "DASH", "EXPE", "LYFT", "TRIP", "UBER"]


def api_key() -> str:
    key = os.environ.get("ALPHAVANTAGE_API_KEY")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "ALPHAVANTAGE_API_KEY":
                key = value.strip()
    if not key:
        raise SystemExit("ALPHAVANTAGE_API_KEY is not set (.env or environment)")
    return key


def fetch(ticker: str, key: str) -> dict:
    query = urllib.parse.urlencode({"function": "EARNINGS", "symbol": ticker, "apikey": key})
    with urllib.request.urlopen(f"https://www.alphavantage.co/query?{query}", timeout=30) as response:
        data = json.load(response)
    if "quarterlyEarnings" not in data:
        raise RuntimeError(f"{ticker}: {data}")
    return {"fetched": date.today().isoformat(), "source": "alphavantage:EARNINGS", "data": data}


def number(text: str | None) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def quarter_of(fiscal_end: str) -> str:
    d = date.fromisoformat(fiscal_end)
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def load(ticker: str) -> dict[str, dict]:
    raw = json.loads((CACHE / f"{ticker}.json").read_text())["data"]
    return {quarter_of(q["fiscalDateEnding"]): {"reported_date": q.get("reportedDate"),
                                                "consensus_eps": number(q.get("estimatedEPS")),
                                                "reported_eps": number(q.get("reportedEPS"))}
            for q in raw["quarterlyEarnings"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", default=TICKERS)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    key = api_key()
    for ticker in args.tickers:
        path = CACHE / f"{ticker}.json"
        if path.exists() and not args.refresh:
            print(f"{ticker}: cached")
            continue
        path.write_text(json.dumps(fetch(ticker, key), indent=1))
        print(f"{ticker}: fetched")
        time.sleep(1.5)


if __name__ == "__main__":
    main()
