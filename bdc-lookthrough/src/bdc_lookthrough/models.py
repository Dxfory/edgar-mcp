"""Typed records returned by the library and MCP tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _dump(obj: Any) -> dict[str, Any]:
    return asdict(obj)


@dataclass(frozen=True)
class FilingSource:
    ticker: str
    company_name: str | None
    cik: int | str | None
    form: str | None
    filing_date: str | None
    report_date: str | None
    accession_number: str | None
    index_url: str | None
    n_holdings: int | None = None
    soi_sum_fair_value: float | None = None
    bs_fair_value: float | None = None
    reconcile_error_pct: float | None = None
    reconcile_ok: bool | None = None
    extraction_method: str = "edgartools_portfolio_investments"


@dataclass
class Holding:
    ticker: str
    cik: int | str | None
    accession_number: str | None
    index_url: str | None
    form: str | None
    period: str | None
    identifier: str | None
    company_name: str
    borrower_norm: str
    aliases: list[str]
    investment_type: str | None
    fair_value: float | None
    cost: float | None
    principal_amount: float | None
    interest_rate: float | None
    pik_rate: float | None
    industry: str | None
    is_debt: bool | None
    extraction_method: str = "edgartools_portfolio_investments"

    def to_dict(self) -> dict[str, Any]:
        return _dump(self)


@dataclass
class OverlapHit:
    query: str
    borrower_keys: list[str]
    bdc_count: int
    tickers: list[str]
    total_fair_value: float
    total_cost: float
    n_positions: int
    positions: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    data_mode: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _dump(self)
