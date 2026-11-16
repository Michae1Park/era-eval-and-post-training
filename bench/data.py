import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from pathlib import Path

import yaml

DEFAULT_AS_OF = "2026-09-01"

FLOW_CONCEPTS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"],
    "net_income": ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "operating_income": ["OperatingIncomeLoss"],
    "diluted_eps": ["EarningsPerShareDiluted"],
    "sales_and_marketing": ["SellingAndMarketingExpense"],
    "research_and_development": ["ResearchAndDevelopmentExpense"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "stock_based_compensation": ["ShareBasedCompensation"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "share_repurchases": ["PaymentsForRepurchaseOfCommonStock"],
}
INSTANT_CONCEPTS = {
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "total_assets": ["Assets"],
}
DURATION_DAYS = {"quarter": (80, 100), "nine_months": (260, 280), "year": (355, 372)}


@dataclass(frozen=True)
class Fact:
    ticker: str
    metric: str
    period: str
    value: float
    unit: str
    fact_id: str
    accession: str
    filed: str

    @property
    def display_unit(self) -> str:
        return "USD" if self.unit == "USD/shares" else "USD millions"

    @property
    def display_value(self) -> float:
        return self.value if self.unit == "USD/shares" else round(self.value / 1e6, 1)


@dataclass(frozen=True)
class Kpi:
    ticker: str
    metric: str
    segment: str | None
    period: str
    value: float
    unit: str
    source: str
    block: str | None
    quote: str
    label_id: str
    target_period: str | None = None


def quarter_key(end: str) -> str:
    d = date.fromisoformat(end)
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def period_order(period: str) -> tuple[int, int]:
    if period.startswith("FY"):
        return int(period[2:]), 5
    return int(period[:4]), int(period[-1])


def shift_year(period: str, years: int) -> str:
    if period.startswith("FY"):
        return f"FY{int(period[2:]) + years}"
    return f"{int(period[:4]) + years}Q{period[-1]}"


@dataclass
class AgentData:
    repo: Path
    as_of: str = DEFAULT_AS_OF
    _facts: dict = field(default_factory=dict)

    @cached_property
    def db(self) -> sqlite3.Connection:
        config = yaml.safe_load((self.repo / "config.yaml").read_text())
        return sqlite3.connect(self.repo / config["db"])

    @cached_property
    def companies(self) -> dict:
        return yaml.safe_load((self.repo / "companies.yaml").read_text())["companies"]

    def short_name(self, ticker: str) -> str:
        aliases = self.companies[ticker].get("aliases") or []
        return aliases[0] if aliases else self.companies[ticker]["name"]

    def sector(self, ticker: str) -> str:
        return self.companies[ticker]["sector"]

    @property
    def tickers(self) -> list[str]:
        return sorted(self.companies)

    def release_date(self, ticker: str, period: str) -> str | None:
        year, quarter = period[:4], f"Q{period[-1]}"
        row = self.db.execute(
            "select filing_date from filings where ticker=? and form='ER' and fiscal_year=? and fiscal_period=?",
            (ticker, int(year), quarter),
        ).fetchone()
        return row[0] if row else None

    def _fact_rows(self, ticker: str, concepts: list[str], span: str | None, as_of: str) -> list[tuple]:
        for concept in concepts:
            if span:
                low, high = DURATION_DAYS[span]
                rows = self.db.execute(
                    "select end, value, unit, id, accession, filed from facts where ticker=? and concept=? "
                    "and dims='{}' and start is not null and julianday(end)-julianday(start) between ? and ? "
                    "and filed<=? order by end, filed",
                    (ticker, concept, low, high, as_of),
                ).fetchall()
            else:
                rows = self.db.execute(
                    "select end, value, unit, id, accession, filed from facts where ticker=? and concept=? "
                    "and dims='{}' and start is null and filed<=? order by end, filed",
                    (ticker, concept, as_of),
                ).fetchall()
            if rows:
                return rows
        return []

    def facts(self, ticker: str, metric: str, span: str | None = "quarter", as_of: str | None = None) -> dict[str, Fact]:
        as_of = as_of or self.as_of
        key = (ticker, metric, span, as_of)
        if key not in self._facts:
            concepts = FLOW_CONCEPTS.get(metric) or INSTANT_CONCEPTS[metric]
            latest = {}
            for end, value, unit, fact_id, accession, filed in self._fact_rows(ticker, concepts, span, as_of):
                period = f"FY{end[:4]}" if span == "year" else quarter_key(end)
                latest[period] = Fact(ticker, metric, period, value, unit, fact_id, accession, filed)
            self._facts[key] = latest
        return self._facts[key]

    @cached_property
    def kpis(self) -> list[Kpi]:
        rows = [json.loads(line) for line in (self.repo / "evaluation/gold/extraction-gold.jsonl").read_text().splitlines() if line.strip()]
        return [Kpi(r["ticker"], r["metric"], r.get("segment"), r["period"], r["value"], r["unit"], r["source"],
                    r.get("block"), r["quote"], r["id"], r.get("target_period")) for r in rows]

    def kpi(self, ticker: str, metric: str, period: str, segment: str | None = None) -> Kpi | None:
        for k in self.kpis:
            if k.ticker == ticker and k.metric == metric and k.period == period and (k.segment or None) == (segment or None):
                return k
        return None

    def children_for(self, ticker: str, form: str, period: str) -> list[tuple[str, str, str]]:
        if period.startswith("FY"):
            year, fiscal_period = int(period[2:]), "FY"
        else:
            year, fiscal_period = int(period[:4]), f"Q{period[-1]}"
        return self.db.execute(
            "select id, parent_id, text from children where ticker=? and form=? and fiscal_year=? and fiscal_period=?",
            (ticker, form, year, fiscal_period),
        ).fetchall()
