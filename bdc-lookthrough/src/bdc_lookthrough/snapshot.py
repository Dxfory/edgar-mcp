"""Load the bundled (or override) SOI snapshot and answer look-through queries."""

from __future__ import annotations

import gzip
import json
import os
from collections import defaultdict
from functools import lru_cache
from importlib.resources import files
from typing import Any

from bdc_lookthrough.jsonutil import jsonable
from bdc_lookthrough.names import aliases_for, is_junk_borrower, normalize_borrower, query_matches

RECONCILE_OK_PCT = 0.03
DEFAULT_TICKERS = ("ARCC", "BXSL", "OBDC")
LIMIT_MIN = 1
LIMIT_MAX = 200
SNAPSHOT_WARNINGS = (
    "Numbers come from a dated public 10-Q/10-K snapshot unless you refresh. Cite accession_number.",
    "Overlap is normalized legal-name matching, not a CUSIP or loan ID. Misses and collisions happen.",
    "SOI row sums can exceed the balance-sheet Investments-at-FV line when XBRL repeats rollups. Use reconcile_to_bs.",
    "Non-accrual is the filer's tagged status, not a rating-agency default rate. PIK can still be accrual.",
)


def _read_json(path: str) -> dict[str, Any]:
    if path.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def bundled_snapshot_path() -> str:
    return str(files("bdc_lookthrough").joinpath("data", "snapshot.json.gz"))


def resolve_snapshot_path(path: str | None = None) -> str:
    override = path or os.environ.get("BDC_LOOKTHROUGH_SNAPSHOT")
    if override:
        return override
    return bundled_snapshot_path()


def clamp_limit(limit: Any, *, default: int = 40) -> int:
    if limit is None:
        limit = default
    try:
        n = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"limit must be an integer from {LIMIT_MIN} to {LIMIT_MAX}") from exc
    if n < LIMIT_MIN or n > LIMIT_MAX:
        raise ValueError(f"limit must be an integer from {LIMIT_MIN} to {LIMIT_MAX}")
    return n


def _enrich_holding(row: dict[str, Any]) -> dict[str, Any]:
    name = str(row.get("company_name") or "")
    aliases = aliases_for(name)
    primary = aliases[0] if aliases else normalize_borrower(name)
    out = dict(row)
    out["borrower_norm"] = primary
    out["aliases"] = aliases
    out["extraction_method"] = row.get("extraction_method") or "edgartools_portfolio_investments"
    return out


class Snapshot:
    def __init__(self, payload: dict[str, Any], *, data_mode: str = "bundled_snapshot"):
        self.raw = payload
        self.data_mode = data_mode
        self.meta: dict[str, Any] = dict(payload.get("snapshot") or {})
        self.universe: list[dict[str, Any]] = list(payload.get("universe") or [])
        self.holdings: list[dict[str, Any]] = [_enrich_holding(row) for row in (payload.get("holdings") or [])]
        self.nonaccrual: list[dict[str, Any]] = list(payload.get("nonaccrual") or [])
        self._by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in self.holdings:
            ticker = str(row.get("ticker") or "").upper()
            if ticker:
                self._by_ticker[ticker].append(row)
        self._universe_by_ticker = {str(item.get("ticker") or "").upper(): item for item in self.universe}

    @classmethod
    def load(cls, path: str | None = None) -> "Snapshot":
        resolved = resolve_snapshot_path(path)
        payload = _read_json(resolved)
        bundled = os.path.abspath(resolved) == os.path.abspath(bundled_snapshot_path())
        mode = "bundled_snapshot" if bundled else "override_snapshot"
        return cls(payload, data_mode=mode)

    def warnings(self, extra: list[str] | None = None) -> list[str]:
        items = [f"data_mode={self.data_mode}"]
        as_of = self.meta.get("as_of_filings")
        if as_of:
            items.append(f"snapshot period {as_of}")
        items.extend(self.meta.get("warnings") or [])
        items.extend(SNAPSHOT_WARNINGS)
        if extra:
            items.extend(extra)
        return items

    def source_for(self, ticker: str) -> dict[str, Any] | None:
        return self._universe_by_ticker.get(ticker.strip().upper())

    def require_ticker(self, ticker: str) -> str:
        key = (ticker or "").strip().upper()
        if key not in self._universe_by_ticker:
            known = ", ".join(sorted(self._universe_by_ticker))
            raise ValueError(f"Unknown BDC ticker {ticker!r}. Snapshot covers: {known or '(empty)'}")
        return key

    def soi(self, ticker: str, *, limit: int = 40, debt_only: bool = False) -> dict[str, Any]:
        key = self.require_ticker(ticker)
        n = clamp_limit(limit, default=40)
        rows = list(self._by_ticker.get(key) or [])
        if debt_only:
            rows = [row for row in rows if row.get("is_debt")]
        rows = sorted(rows, key=lambda item: abs(float(item.get("fair_value") or 0)), reverse=True)
        source = dict(self.source_for(key) or {})
        clipped = [jsonable(_public_holding(row)) for row in rows[:n]]
        return {
            "data_mode": self.data_mode,
            "source": jsonable(source),
            "n_holdings": len(self._by_ticker.get(key) or []),
            "n_returned": len(clipped),
            "holdings": clipped,
            "warnings": self.warnings(
                [
                    "Holdings are truncated by `limit` (largest |fair_value| first). n_holdings is the full count.",
                ]
            ),
        }

    def overlap(self, query: str, *, limit: int = 40) -> dict[str, Any]:
        q_raw = (query or "").strip()
        q_norm = normalize_borrower(q_raw)
        n = clamp_limit(limit, default=40)
        if len(q_norm) < 3:
            raise ValueError("borrower query must have at least 3 letters after normalization")
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in self.holdings:
            names = list(row.get("aliases") or [])
            if is_junk_borrower(row.get("borrower_norm")):
                continue
            if query_matches(q_norm, names):
                groups[str(row.get("borrower_norm") or "")].append(row)
        if not groups:
            return {
                "query": q_raw,
                "borrower_norm": q_norm,
                "bdc_count": 0,
                "tickers": [],
                "total_fair_value": 0.0,
                "total_cost": 0.0,
                "n_positions": 0,
                "positions": [],
                "sources": [],
                "data_mode": self.data_mode,
                "warnings": self.warnings(["No snapshot row matched. Try the legal name as filed, not a brand nickname."]),
            }
        positions: list[dict[str, Any]] = []
        keys = sorted(groups)
        for key in keys:
            positions.extend(groups[key])
        positions = sorted(positions, key=lambda item: abs(float(item.get("fair_value") or 0)), reverse=True)
        tickers = sorted({str(row.get("ticker")) for row in positions if row.get("ticker")})
        sources = []
        seen_acc: set[str] = set()
        for row in positions:
            acc = str(row.get("accession_number") or "")
            if acc in seen_acc:
                continue
            seen_acc.add(acc)
            src = self.source_for(str(row.get("ticker") or "")) or {}
            sources.append(
                jsonable(
                    {
                        "ticker": row.get("ticker"),
                        "accession_number": row.get("accession_number"),
                        "index_url": row.get("index_url"),
                        "form": row.get("form"),
                        "period": row.get("period"),
                        "company_name": src.get("company_name"),
                    }
                )
            )
        returned = [jsonable(_public_holding(row)) for row in positions[:n]]
        extra = []
        if len(tickers) == 1:
            extra.append("Only one BDC in this snapshot matched. That is not proof the loan is unique to them.")
        return {
            "query": q_raw,
            "borrower_norm": q_norm,
            "borrower_keys": keys,
            "bdc_count": len(tickers),
            "tickers": tickers,
            "total_fair_value": float(sum(float(row.get("fair_value") or 0) for row in positions)),
            "total_cost": float(sum(float(row.get("cost") or 0) for row in positions)),
            "n_positions": len(positions),
            "positions": returned,
            "sources": sources,
            "data_mode": self.data_mode,
            "warnings": self.warnings(extra),
        }

    def nonaccrual_names(self, ticker: str | None = None) -> dict[str, Any]:
        rows = list(self.nonaccrual)
        key = (ticker or "").strip()
        if key:
            key = self.require_ticker(key)
            rows = [item for item in rows if str(item.get("ticker") or "").upper() == key]
        named: list[dict[str, Any]] = []
        for block in rows:
            method = block.get("extraction_method") or "none"
            source = {
                "ticker": block.get("ticker"),
                "accession_number": block.get("accession_number"),
                "index_url": block.get("index_url"),
                "period": block.get("period"),
                "extraction_method": method,
                "nonaccrual_rate": block.get("nonaccrual_rate"),
                "nonaccrual_fair_value": block.get("nonaccrual_fair_value"),
                "total_portfolio_fair_value": block.get("total_portfolio_fair_value"),
                "num_nonaccrual": block.get("num_nonaccrual"),
            }
            for inv in block.get("investments") or []:
                name = str(inv.get("company_name") or "")
                named.append(
                    jsonable(
                        {
                            **source,
                            "company_name": name,
                            "borrower_norm": (aliases_for(name) or [normalize_borrower(name)])[0],
                            "identifier": inv.get("identifier"),
                            "investment_type": inv.get("investment_type"),
                            "fair_value": inv.get("fair_value"),
                            "cost": inv.get("cost"),
                            "footnote_text": inv.get("footnote_text"),
                        }
                    )
                )
        extra = []
        if any((item.get("extraction_method") or "none") == "none" for item in rows):
            extra.append("extraction_method=none is a parse gap, not proof the book is clean.")
        if not rows:
            extra.append("No non-accrual block in this snapshot for that ticker.")
        return {
            "data_mode": self.data_mode,
            "count": len(named),
            "investments": named[:80],
            "blocks": [
                jsonable(
                    {
                        "ticker": item.get("ticker"),
                        "accession_number": item.get("accession_number"),
                        "index_url": item.get("index_url"),
                        "period": item.get("period"),
                        "extraction_method": item.get("extraction_method"),
                        "nonaccrual_rate": item.get("nonaccrual_rate"),
                        "nonaccrual_rate_pct": None
                        if item.get("nonaccrual_rate") is None
                        else round(float(item["nonaccrual_rate"]) * 100, 4),
                        "num_nonaccrual": item.get("num_nonaccrual"),
                    }
                )
                for item in rows
            ],
            "warnings": self.warnings(extra),
        }

    def reconcile(self, ticker: str) -> dict[str, Any]:
        key = self.require_ticker(ticker)
        source = dict(self.source_for(key) or {})
        rows = self._by_ticker.get(key) or []
        soi_sum = float(sum(float(row.get("fair_value") or 0) for row in rows))
        bs = source.get("bs_fair_value")
        error_pct = None
        ok = None
        if bs not in (None, 0, 0.0):
            error_pct = (soi_sum - float(bs)) / float(bs)
            ok = abs(error_pct) <= RECONCILE_OK_PCT
        extra = [
            f"OK threshold is abs(error_pct) <= {RECONCILE_OK_PCT:.0%}.",
            "bs_fair_value is undimensioned us-gaap:InvestmentOwnedAtFairValue on the balance sheet.",
        ]
        if ok is False:
            extra.append(
                "Gap usually means XBRL SOI rows include company rollups or unclassified repeats. "
                "Do not treat soi_sum_fair_value as NAV."
            )
        return {
            "data_mode": self.data_mode,
            "ticker": key,
            "source": jsonable(source),
            "n_holdings": len(rows),
            "soi_sum_fair_value": soi_sum,
            "bs_fair_value": jsonable(bs),
            "reconcile_error_pct": jsonable(None if error_pct is None else round(float(error_pct), 6)),
            "reconcile_ok": ok,
            "extraction_method": "soi_sum_vs_bs_InvestmentOwnedAtFairValue",
            "warnings": self.warnings(extra),
        }


def _public_holding(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "ticker",
        "cik",
        "accession_number",
        "index_url",
        "form",
        "period",
        "identifier",
        "company_name",
        "borrower_norm",
        "aliases",
        "investment_type",
        "fair_value",
        "cost",
        "principal_amount",
        "interest_rate",
        "pik_rate",
        "industry",
        "is_debt",
        "extraction_method",
    )
    return {key: row.get(key) for key in keys}


@lru_cache(maxsize=4)
def load_snapshot(path: str | None = None) -> Snapshot:
    return Snapshot.load(path)


def reset_snapshot_cache() -> None:
    load_snapshot.cache_clear()
