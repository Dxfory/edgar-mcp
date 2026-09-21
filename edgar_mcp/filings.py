"""Thin edgartools accessors. Public SEC filings only."""

from __future__ import annotations

import os
from typing import Any

from edgar_mcp.jsonutil import get_field, jsonable

_IDENTITY_DONE = False
_WARM = False

ALLOWED_FORMS = ("10-K", "10-Q")

SEGMENT_AXES = (
    "ProductOrServiceAxis",
    "StatementBusinessSegmentsAxis",
    "SegmentReportingInformationAxis",
    "StatementGeographicalAxis",
    "GeographicalAxis",
)

REVENUE_CONCEPTS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
)

FORM4_CODES: dict[str, tuple[str, bool]] = {
    "P": ("open-market buy", True),
    "S": ("open-market sell", True),
    "A": ("grant / award", False),
    "M": ("option exercise", False),
    "F": ("tax withholding", False),
    "C": ("conversion", False),
    "G": ("gift", False),
    "D": ("disposition to issuer", False),
    "J": ("other", False),
}


class EdgarConfigError(RuntimeError):
    pass


def ensure_identity() -> str:
    global _IDENTITY_DONE
    ident = (os.environ.get("EDGAR_IDENTITY") or "").strip()
    if not ident or "@" not in ident:
        raise EdgarConfigError(
            "Set EDGAR_IDENTITY to 'Name you@email.com'. "
            "The SEC requires a User-Agent with a contact email."
        )
    if not _IDENTITY_DONE:
        from edgar import set_identity

        set_identity(ident)
        _IDENTITY_DONE = True
    return ident


def warmup() -> None:
    """Prefetch the ticker→CIK table so the first MCP tool call is not the cache miss."""
    global _WARM
    if _WARM:
        return
    ensure_identity()
    from edgar.reference.tickers import get_company_tickers

    get_company_tickers()
    _WARM = True


def normalize_form(form: str | None) -> str:
    raw = (form or "10-K").strip().upper()
    if raw not in ALLOWED_FORMS:
        raise ValueError("form must be 10-K or 10-Q")
    return raw


def classify_form4_code(code: Any) -> dict[str, Any]:
    text = str(code or "").strip().upper()
    meaning, open_market = FORM4_CODES.get(text, ("unknown / see filing", False))
    if text == "":
        return {"code": None, "code_meaning": meaning, "open_market": False}
    return {"code": text, "code_meaning": meaning, "open_market": open_market}


def resolve_company(ticker_or_cik: str) -> Any:
    from edgar import Company

    key = ticker_or_cik.strip()
    if not key:
        raise ValueError("ticker_or_cik is empty")
    company = Company(key)
    if company is None:
        raise ValueError(f"No SEC company matched {key!r}")
    return company


def latest_filing(company: Any, form: str, accession: str | None = None) -> Any:
    kwargs: dict[str, Any] = {"form": form}
    if accession:
        kwargs["accession_number"] = accession
    filings = company.get_filings(**kwargs)
    latest = getattr(filings, "latest", None)
    if callable(latest):
        filing = latest()
        if filing is not None:
            return filing
    if accession is None and hasattr(company, "latest"):
        try:
            filing = company.latest(form)
            if filing is not None:
                return filing
        except TypeError:
            filing = company.latest(form=form)
            if filing is not None:
                return filing
    head = filings.head(1)
    try:
        return head[0]
    except Exception as exc:
        extra = f" accession={accession}" if accession else ""
        raise ValueError(f"No {form} filing found{extra}") from exc


def filing_meta(filing: Any, company: Any) -> dict[str, Any]:
    cik = get_field(filing, "cik", default=get_field(company, "cik"))
    accession = get_field(filing, "accession_no", "accession_number", "accession")
    acc_nodash = str(accession).replace("-", "") if accession else None
    cik_num = str(cik).lstrip("0") if cik is not None else None
    index_url = None
    if cik_num and acc_nodash:
        index_url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_nodash}/"
            f"{accession}-index.html"
        )
    return {
        "company_name": get_field(company, "name", "company_name"),
        "cik": jsonable(cik),
        "ticker_query": get_field(company, "tickers", "ticker"),
        "form": get_field(filing, "form"),
        "filing_date": jsonable(get_field(filing, "filing_date", "filingDate")),
        "report_date": jsonable(get_field(filing, "report_date", "period_of_report")),
        "accession_number": jsonable(accession),
        "index_url": index_url,
    }


def load_xbrl(filing: Any) -> Any:
    xbrl = filing.xbrl()
    if xbrl is None:
        raise ValueError("This filing has no XBRL instance")
    return xbrl


def _fact_record(fact: Any) -> dict[str, Any]:
    if isinstance(fact, dict):
        data = dict(fact)
    else:
        data = {}
        for key in (
            "concept",
            "label",
            "value",
            "period_end",
            "period_start",
            "period_type",
            "units",
            "decimals",
            "dimensions",
            "context_ref",
            "statement",
        ):
            if hasattr(fact, key):
                data[key] = getattr(fact, key)
    return {k: jsonable(v) for k, v in data.items()}


def _query(xbrl: Any, **kwargs: Any) -> list[Any]:
    q = xbrl.query()
    concept = kwargs.get("concept")
    if concept:
        exact = bool(kwargs.get("exact", False))
        q = q.by_concept(concept, exact=exact)
    axis = kwargs.get("axis")
    if axis:
        q = q.by_dimension(axis)
    if hasattr(q, "execute"):
        return list(q.execute())
    return list(q)


def collect_trading_symbols(facts: list[Any], entity_info: Any) -> dict[str, Any]:
    """Build the ticker payload from XBRL facts. entity_info.ticker is last-wins."""
    symbols = []
    seen: set[str] = set()
    for fact in facts:
        rec = _fact_record(fact)
        value = rec.get("value")
        if value is None or str(value).strip() == "":
            continue
        key = f"{value}|{rec.get('context_ref')}|{rec.get('dimensions')}"
        if key in seen:
            continue
        seen.add(key)
        symbols.append(
            {
                "symbol": str(value).strip(),
                "concept": rec.get("concept"),
                "context_ref": rec.get("context_ref"),
                "dimensions": rec.get("dimensions"),
                "period_end": rec.get("period_end"),
            }
        )
    scalar = None
    if isinstance(entity_info, dict):
        scalar = entity_info.get("ticker")
    return {
        "entity_info_ticker": jsonable(scalar),
        "trading_symbols": symbols,
        "warnings": [
            "entity_info_ticker is a single scalar. On multi-security 10-Ks it is last-wins "
            "in document order (for example a preferred or note ticker can replace the common symbol).",
            "Use trading_symbols for every dei:TradingSymbol fact, including class-of-stock dimensions.",
        ],
    }


def trading_symbols(
    ticker_or_cik: str,
    accession: str | None = None,
    form: str | None = "10-K",
) -> dict[str, Any]:
    ensure_identity()
    form = normalize_form(form)
    company = resolve_company(ticker_or_cik)
    filing = latest_filing(company, form, accession=accession)
    xbrl = load_xbrl(filing)
    info = get_field(xbrl, "entity_info", default={})
    if callable(info):
        info = info()
    facts = _query(xbrl, concept="dei:TradingSymbol", exact=True)
    if not facts:
        facts = _query(xbrl, concept="TradingSymbol", exact=False)
    payload = collect_trading_symbols(facts, info or {})
    payload["source"] = filing_meta(filing, company)
    return payload


def _is_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            return None
        return float(value)
    text = str(value).strip().replace(",", "")
    if text == "" or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def collect_segment_rows(axis: str, facts: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fact in facts:
        rec = _fact_record(fact)
        amount = _is_number(rec.get("value"))
        if amount is None:
            continue
        key = f"{axis}|{rec.get('concept')}|{rec.get('dimensions')}|{rec.get('period_end')}|{amount}"
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "axis": axis,
                "concept": rec.get("concept"),
                "label": rec.get("label"),
                "value": amount,
                "period_start": rec.get("period_start"),
                "period_end": rec.get("period_end"),
                "units": rec.get("units"),
                "dimensions": rec.get("dimensions"),
            }
        )
    return rows


def segment_revenue(
    ticker_or_cik: str,
    accession: str | None = None,
    form: str | None = "10-K",
) -> dict[str, Any]:
    ensure_identity()
    form = normalize_form(form)
    company = resolve_company(ticker_or_cik)
    filing = latest_filing(company, form, accession=accession)
    xbrl = load_xbrl(filing)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for axis in SEGMENT_AXES:
        for concept in REVENUE_CONCEPTS:
            try:
                facts = _query(xbrl, concept=concept, exact=False, axis=axis)
            except Exception:
                continue
            for row in collect_segment_rows(axis, facts):
                key = f"{row['axis']}|{row.get('concept')}|{row.get('dimensions')}|{row.get('period_end')}|{row['value']}"
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
    rows.sort(key=lambda r: (str(r.get("period_end") or ""), -abs(float(r["value"]))))
    return {
        "source": filing_meta(filing, company),
        "segments": rows[:80],
        "warnings": [
            "Segment mix is not in get_financials(). These rows are dimensioned XBRL revenue facts.",
            "StatementView.DETAILED can drop reportable-segment lines on some 10-Ks; this tool does not use that view.",
            "Issuers tag segments with different axes and concepts. Empty rows means the filing likely only has narrative notes.",
        ],
    }


def _transaction_row(item: Any) -> dict[str, Any]:
    classified = classify_form4_code(get_field(item, "code"))
    return {
        "transaction_type": jsonable(get_field(item, "transaction_type")),
        "code": classified["code"],
        "code_meaning": classified["code_meaning"],
        "open_market": classified["open_market"],
        "shares": jsonable(get_field(item, "shares")),
        "price_per_share": jsonable(get_field(item, "price_per_share")),
        "value": jsonable(get_field(item, "value")),
        "security_type": jsonable(get_field(item, "security_type")),
        "security_title": jsonable(get_field(item, "security_title")),
    }


def form4_filings(ticker_or_cik: str, limit: int = 8) -> dict[str, Any]:
    ensure_identity()
    company = resolve_company(ticker_or_cik)
    n = max(1, min(int(limit), 20))
    filings = company.get_filings(form="4").head(n)
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    code_counts: dict[str, int] = {}
    for filing in filings:
        try:
            form4 = filing.obj()
            summary = form4.get_ownership_summary()
            transactions = get_field(summary, "transactions", default=[]) or []
            rows = [_transaction_row(t) for t in list(transactions)[:12]]
            for row in rows:
                code = row.get("code")
                if code:
                    code_counts[str(code)] = code_counts.get(str(code), 0) + 1
            results.append(
                {
                    "source": filing_meta(filing, company),
                    "insider_name": jsonable(get_field(summary, "insider_name")),
                    "position": jsonable(get_field(summary, "position")),
                    "primary_activity": jsonable(get_field(summary, "primary_activity")),
                    "net_change": jsonable(get_field(summary, "net_change")),
                    "net_value": jsonable(get_field(summary, "net_value")),
                    "reporting_date": jsonable(get_field(summary, "reporting_date")),
                    "remaining_shares": jsonable(get_field(summary, "remaining_shares")),
                    "transactions": rows,
                }
            )
        except Exception as exc:
            acc = get_field(filing, "accession_no", "accession_number", default="unknown")
            errors.append(f"{acc}: {exc}")
    return {
        "company_name": jsonable(get_field(company, "name")),
        "cik": jsonable(get_field(company, "cik")),
        "count": len(results),
        "code_counts": code_counts,
        "filings": results,
        "warnings": [
            "Form 4 codes: P open-market buy, S open-market sell, A grant, M option exercise, F tax withholding.",
            "open_market is false for A/M/F. Awards and option exercises are not open-market purchases.",
            *errors,
        ],
    }
