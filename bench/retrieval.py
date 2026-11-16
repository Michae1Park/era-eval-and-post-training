import re
from functools import lru_cache

from data import AgentData

MIN_QUOTE_CHARS = 12


def normalize(text: str) -> str:
    text = text.lower().replace("$", "").replace("|", " ").replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


def quote_cells(quote: str) -> list[str]:
    cells = [normalize(c) for c in quote.split("|")]
    return [c for c in cells if c]


def period_of(item: dict) -> str | None:
    if item.get("period"):
        return item["period"]
    if item.get("fiscal_year"):
        return f"FY{item['fiscal_year']}"
    return None


class ChunkIndex:
    def __init__(self, data: AgentData):
        self.data = data

    @lru_cache(maxsize=None)
    def chunks(self, ticker: str, form: str, period: str) -> tuple:
        return tuple((cid, pid, normalize(text)) for cid, pid, text in self.data.children_for(ticker, form, period))

    def match(self, ticker: str, form: str, period: str, quote: str) -> list[tuple[str, str]]:
        whole = normalize(quote)
        cells = quote_cells(quote)
        hits = []
        for cid, pid, text in self.chunks(ticker, form, period):
            if len(whole) >= MIN_QUOTE_CHARS and whole in text:
                hits.append((cid, pid))
            elif len(cells) >= 2 and all(c in text for c in cells):
                hits.append((cid, pid))
        return hits

    def parent_of(self, child_id: str) -> str | None:
        row = self.data.db.execute("select parent_id from children where id=?", (child_id,)).fetchone()
        return row[0] if row else None


def attach_retrieval_gold(tasks: list[dict], index: ChunkIndex) -> dict:
    stats = {"with_quotes": 0, "matched": 0}
    for t in tasks:
        evidence = t["evidence"]
        children = list(evidence["chunk_ids"])
        quotes = [g for g in evidence["gold"] if g.get("evidence")]
        if quotes:
            stats["with_quotes"] += 1
        for g in quotes:
            period = period_of(g)
            ticker = g.get("company")
            if not (period and ticker):
                continue
            form = g.get("form") or ("10-K" if period.startswith("FY") else "ER")
            children += [cid for cid, _ in index.match(ticker, form, period, g["evidence"])]
        children = list(dict.fromkeys(children))
        parents = list(dict.fromkeys(p for p in (index.parent_of(c) for c in children) if p))
        evidence["chunk_ids"] = children
        evidence["parent_chunk_ids"] = parents
        if quotes and children:
            stats["matched"] += 1
        if children and t["mode"] != "extraction" and "retrieval" not in t["layers"]:
            t["layers"] = sorted(set(t["layers"]) | {"retrieval", "generation"})
    return stats
