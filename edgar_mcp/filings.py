"""Thin edgartools accessors. Public SEC filings only."""

from __future__ import annotations

import logging
import os
from typing import Any

from edgar_mcp.jsonutil import get_field, jsonable

_IDENTITY_DONE = False
_WARM = False
_IDENTITY_LOG_FILTER = False

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


class _RedactIdentityFilter(logging.Filter):
    """Keep EDGAR_IDENTITY off stderr. edgartools logs it at INFO on set_identity."""

    def filter(self, record: logging.LogRecord) -> bool:
        ident = (os.environ.get("EDGAR_IDENTITY") or "").strip()
        if not ident:
            return True
        msg = record.getMessage()
        if ident in msg:
            record.msg = msg.replace(ident, "<redacted>")
            record.args = ()
        return True


def _install_identity_log_filter() -> None:
    """Attach redaction to handlers. Logger filters do not run for child loggers like edgar.settings."""
    global _IDENTITY_LOG_FILTER
    handlers: list[logging.Handler] = list(logging.getLogger().handlers)
    if logging.lastResort is not None:
        handlers.append(logging.lastResort)
    for handler in handlers:
        if handler is None:
            continue
        if any(isinstance(item, _RedactIdentityFilter) for item in handler.filters):
            continue
        handler.addFilter(_RedactIdentityFilter())
    _IDENTITY_LOG_FILTER = True


def ensure_identity() -> str:
    global _IDENTITY_DONE
    ident = (os.environ.get("EDGAR_IDENTITY") or "").strip()
    if not ident or "@" not in ident:
        raise EdgarConfigError(
            "Set EDGAR_IDENTITY to 'Name you@email.com'. "
            "The SEC requires a User-Agent with a contact email."
        )
    if not _IDENTITY_DONE:
        _install_identity_log_filter()
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

    logging.info("warmup: fetching EDGAR ticker cache")
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


def prefer_original_form(filings_list: list[Any], form: str) -> Any | None:
    """10-K/A is often newer than 10-K and can omit Schedule-of-Investments XBRL."""
    rows = [item for item in filings_list if item is not None]
    if not rows:
        return None
    exact = [item for item in rows if str(get_field(item, "form") or "") == form]
    if exact:
        return exact[0]
    return rows[0]


def _head_filings(filings: Any, limit: int = 20) -> list[Any]:
    try:
        head = filings.head(limit)
    except Exception:
        try:
            return list(filings)[:limit]
        except Exception:
            return []
    try:
        return list(head)
    except TypeError:
        try:
            return [head[i] for i in range(limit)]
        except Exception:
            return []


def latest_filing(company: Any, form: str, accession: str | None = None) -> Any:
    kwargs: dict[str, Any] = {"form": form}
    if accession:
        kwargs["accession_number"] = accession
    filings = company.get_filings(**kwargs)
    if accession is None:
        picked = prefer_original_form(_head_filings(filings), form)
        if picked is not None:
            return picked
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


def _clip(text: Any, limit: int = 400) -> str | None:
    if text is None:
        return None
    value = str(text).strip()
    if value == "":
        return None
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3] + "..."


def _cik_int(value: Any) -> int:
    text = str(value or "").strip().lstrip("0")
    if text == "":
        return 0
    try:
        return int(text)
    except ValueError:
        return 0


def require_bdc(company: Any) -> int:
    """Refuse operating companies. Non-accrual is a BDC Schedule-of-Investments fact."""
    from edgar.bdc import is_bdc_cik

    cik = _cik_int(get_field(company, "cik"))
    name = get_field(company, "name") or cik
    if cik == 0 or not is_bdc_cik(cik):
        raise ValueError(
            f"{name} is not on the SEC BDC (814-) list. "
            "get_bdc_nonaccrual only reads Business Development Company filings. "
            "It does not estimate private-credit quality for operating companies."
        )
    return cik


def serialize_nonaccrual(result: Any, source: dict[str, Any]) -> dict[str, Any]:
    """Shape edgartools NonAccrualResult for MCP. Duck-typed so tests stay offline."""
    investments: list[dict[str, Any]] = []
    for inv in list(getattr(result, "investments", None) or [])[:40]:
        investments.append(
            {
                "identifier": jsonable(getattr(inv, "identifier", None)),
                "company_name": jsonable(getattr(inv, "company_name", None)),
                "investment_type": jsonable(getattr(inv, "investment_type", None)),
                "fair_value": jsonable(getattr(inv, "fair_value", None)),
                "cost": jsonable(getattr(inv, "cost", None)),
                "footnote_text": _clip(getattr(inv, "footnote_text", None)),
            }
        )
    rate = getattr(result, "nonaccrual_rate", None)
    method = getattr(result, "extraction_method", None) or "none"
    extractor_warnings = [str(item) for item in (getattr(result, "warnings", None) or [])]
    return {
        "source": source,
        "extraction_method": method,
        "nonaccrual_rate": jsonable(rate),
        "nonaccrual_rate_pct": None if rate is None else round(float(rate) * 100, 4),
        "nonaccrual_fair_value": jsonable(getattr(result, "nonaccrual_fair_value", None)),
        "total_portfolio_fair_value": jsonable(
            getattr(result, "total_portfolio_fair_value", None)
        ),
        "num_nonaccrual": int(getattr(result, "num_nonaccrual", len(investments)) or 0),
        "custom_concept_rate": jsonable(getattr(result, "custom_concept_rate", None)),
        "aggregate_concept_value": jsonable(getattr(result, "aggregate_concept_value", None)),
        "investments": investments,
        "warnings": [
            "Non-accrual is the filer's tagged status, not a Fitch private-credit default rate.",
            "Loans can still be 'accrual' while paying PIK or after a distressed extension.",
            "extraction_method footnote > custom_concept > aggregate_concept > none. none is not proof of zero.",
            "A zero rate with extractor warnings is a parse gap until you read the filing.",
            *extractor_warnings,
        ],
    }


def bdc_nonaccrual(
    ticker_or_cik: str,
    accession: str | None = None,
    form: str | None = "10-K",
) -> dict[str, Any]:
    ensure_identity()
    form = normalize_form(form)
    company = resolve_company(ticker_or_cik)
    require_bdc(company)
    filing = latest_filing(company, form, accession=accession)
    from edgar.bdc.nonaccrual import extract_nonaccrual

    result = extract_nonaccrual(filing)
    if result is None:
        raise ValueError(
            f"No XBRL non-accrual extract for this {form}. "
            "Open the index_url and read the Schedule of Investments footnotes."
        )
    payload = serialize_nonaccrual(result, filing_meta(filing, company))
    if result.extraction_method == "none" and result.num_nonaccrual == 0:
        payload["warnings"].append(
            "Extractor found no non-accrual signal. Confirm in the filing before treating this as 0%."
        )
    return payload
