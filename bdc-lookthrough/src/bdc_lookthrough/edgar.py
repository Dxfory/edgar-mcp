"""Optional live refresh from SEC EDGAR via edgartools. Not used by default MCP."""

from __future__ import annotations

import gzip
import json
import os
from datetime import date
from decimal import Decimal
from typing import Any

from bdc_lookthrough.snapshot import DEFAULT_TICKERS


class EdgarConfigError(RuntimeError):
    pass


def ensure_identity() -> str:
    ident = (os.environ.get("EDGAR_IDENTITY") or "").strip()
    if not ident or "@" not in ident:
        raise EdgarConfigError(
            "Set EDGAR_IDENTITY to 'Name you@email.com'. "
            "The SEC requires a User-Agent with a contact email."
        )
    from edgar import set_identity

    set_identity(ident)
    return ident


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            return None
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _index_url(cik: Any, accession: Any) -> str | None:
    if cik is None or accession is None:
        return None
    cik_num = str(cik).lstrip("0")
    acc = str(accession)
    acc_nodash = acc.replace("-", "")
    if not cik_num or not acc_nodash:
        return None
    return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_nodash}/{acc}-index.html"


def _bs_investments_fv(xbrl: Any, period: str | None) -> float | None:
    try:
        query = xbrl.query().by_concept("InvestmentOwnedAtFairValue", exact=False)
        rows = list(query.execute()) if hasattr(query, "execute") else list(query)
    except Exception:
        return None
    want = (period or "")[:10]
    undim: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("statement_type") != "BalanceSheet":
            continue
        inst = str(row.get("period_instant") or "")[:10]
        if want and inst and inst != want:
            continue
        if row.get("is_dimensioned"):
            continue
        amount = _num(row.get("numeric_value"))
        if amount:
            undim.append(amount)
    if not undim:
        return None
    undim.sort()
    return undim[len(undim) // 2]


def _holding_row(ticker: str, source: dict[str, Any], item: Any) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "cik": source.get("cik"),
        "accession_number": source.get("accession_number"),
        "index_url": source.get("index_url"),
        "form": source.get("form"),
        "period": source.get("report_date"),
        "identifier": getattr(item, "identifier", None),
        "company_name": getattr(item, "company_name", None),
        "investment_type": getattr(item, "investment_type", None),
        "fair_value": _num(getattr(item, "fair_value", None)),
        "cost": _num(getattr(item, "cost", None)),
        "principal_amount": _num(getattr(item, "principal_amount", None)),
        "interest_rate": getattr(item, "interest_rate", None),
        "pik_rate": getattr(item, "pik_rate", None),
        "industry": getattr(item, "industry", None),
        "is_debt": bool(getattr(item, "is_debt", False)),
        "extraction_method": "edgartools_portfolio_investments",
    }


def refresh_snapshot(
    tickers: list[str] | tuple[str, ...] = DEFAULT_TICKERS,
    *,
    form_order: tuple[str, ...] = ("10-Q", "10-K"),
) -> dict[str, Any]:
    """Pull latest SOI + non-accrual + BS FV for the v1 BDC universe."""
    ensure_identity()
    from edgar.bdc import extract_nonaccrual, get_bdc_list

    bdcs = get_bdc_list()
    universe: list[dict[str, Any]] = []
    holdings: list[dict[str, Any]] = []
    nonaccrual: list[dict[str, Any]] = []
    for ticker in [item.strip().upper() for item in tickers if item.strip()]:
        entity = bdcs.get_by_ticker(ticker)
        if entity is None:
            raise ValueError(f"{ticker} is not on the SEC BDC (814-) list")
        company = entity.get_company()
        investments = None
        form_used = None
        filing = None
        for form in form_order:
            investments = entity.portfolio_investments(form=form)
            if investments is None or len(investments) == 0:
                continue
            filings = company.get_filings(form=form, amendments=False)
            if len(filings) == 0:
                continue
            filing = filings[0]
            form_used = form
            break
        if investments is None or filing is None or form_used is None:
            raise ValueError(f"No detailed Schedule of Investments for {ticker}")
        accession = getattr(filing, "accession_no", None) or getattr(filing, "accession_number", None)
        report_date = str(getattr(filing, "report_date", None) or getattr(filing, "period_of_report", None) or "")
        cik = getattr(company, "cik", None)
        xbrl = filing.xbrl()
        bs_fv = _bs_investments_fv(xbrl, report_date) if xbrl is not None else None
        soi_sum = _num(getattr(investments, "total_fair_value", None))
        error_pct = None
        ok = None
        if bs_fv not in (None, 0):
            error_pct = ((soi_sum or 0) - bs_fv) / bs_fv
            ok = abs(error_pct) <= 0.03
        source = {
            "ticker": ticker,
            "company_name": getattr(company, "name", None),
            "cik": int(str(cik)) if str(cik).isdigit() else cik,
            "form": form_used,
            "filing_date": str(getattr(filing, "filing_date", None) or ""),
            "report_date": report_date,
            "accession_number": str(accession) if accession else None,
            "index_url": _index_url(cik, accession),
            "n_holdings": len(investments),
            "total_fair_value": soi_sum,
            "total_cost": _num(getattr(investments, "total_cost", None)),
            "bs_fair_value": bs_fv,
            "reconcile_error_pct": error_pct,
            "reconcile_ok": ok,
        }
        universe.append(source)
        for item in investments:
            holdings.append(_holding_row(ticker, source, item))
        try:
            result = extract_nonaccrual(filing)
        except Exception:
            result = None
        if result is None:
            continue
        nonaccrual.append(
            {
                "ticker": ticker,
                "accession_number": source["accession_number"],
                "index_url": source["index_url"],
                "period": report_date,
                "extraction_method": getattr(result, "extraction_method", None) or "none",
                "nonaccrual_rate": _num(getattr(result, "nonaccrual_rate", None)),
                "nonaccrual_fair_value": _num(getattr(result, "nonaccrual_fair_value", None)),
                "total_portfolio_fair_value": _num(getattr(result, "total_portfolio_fair_value", None)),
                "num_nonaccrual": int(getattr(result, "num_nonaccrual", 0) or 0),
                "investments": [
                    {
                        "identifier": getattr(inv, "identifier", None),
                        "company_name": getattr(inv, "company_name", None),
                        "investment_type": getattr(inv, "investment_type", None),
                        "fair_value": _num(getattr(inv, "fair_value", None)),
                        "cost": _num(getattr(inv, "cost", None)),
                        "footnote_text": (getattr(inv, "footnote_text", None) or "")[:400],
                    }
                    for inv in list(getattr(result, "investments", None) or [])[:80]
                ],
                "warnings": [str(item) for item in (getattr(result, "warnings", None) or [])],
            }
        )
    return {
        "snapshot": {
            "id": f"bdc-lookthrough-live-{date.today().isoformat()}",
            "as_of_filings": next((item.get("report_date") for item in universe if item.get("report_date")), None),
            "tickers": [item["ticker"] for item in universe],
            "source": "SEC EDGAR via edgartools (live refresh)",
            "warnings": [
                "Live extract. Still public filings only — not a NAV tape or CV pricing feed.",
                "SOI row sums can exceed the balance-sheet Investments-at-FV line when XBRL repeats rollups.",
            ],
        },
        "universe": universe,
        "holdings": holdings,
        "nonaccrual": nonaccrual,
    }


def write_snapshot(payload: dict[str, Any], path: str) -> str:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
    return path
