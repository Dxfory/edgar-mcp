"""MCP server: SEC 10-K/10-Q symbols, segment revenue, BDC non-accrual, Form 4."""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from edgar_mcp import __version__
from edgar_mcp.filings import (
    EdgarConfigError,
    bdc_nonaccrual,
    form4_filings,
    segment_revenue,
    trading_symbols,
    warmup,
)

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s")


@asynccontextmanager
async def _lifespan(_server: FastMCP) -> AsyncIterator[dict]:
    try:
        warmup()
        logging.info("EDGAR ticker cache warmed")
    except EdgarConfigError as exc:
        logging.warning("warmup skipped: %s", exc)
    except Exception:
        logging.exception("warmup failed")
    yield {}


mcp = FastMCP(
    "edgar-filings",
    instructions=(
        "Read numbers from SEC EDGAR 10-K/10-Q XBRL and Form 4 via edgartools. "
        "Always cite accession_number and index_url. "
        "Do not invent segment mix, insider trades, or BDC credit quality. "
        "entity_info_ticker can be the wrong class on multi-security filings; prefer trading_symbols. "
        "Form 4 A/M/F are not open-market trades; trust open_market=false. "
        "BDC non-accrual is not a default rate; PIK and amend-and-extend can still be accrual."
    ),
    lifespan=_lifespan,
)
# FastMCP does not take version=; initialize should report this package, not mcp's.
mcp._mcp_server.version = __version__


def _fail(exc: Exception) -> dict:
    return {"error": f"{type(exc).__name__}: {exc}"}


def _run_tool(name: str, fn: Callable[..., dict], **kwargs: Any) -> dict:
    started = time.perf_counter()
    ticker = kwargs.get("ticker_or_cik")
    form = kwargs.get("form")
    extra = f" ticker={ticker}" if ticker else ""
    if form:
        extra += f" form={form}"
    logging.info("%s start%s", name, extra)
    try:
        payload = fn(**kwargs)
        logging.info("%s ok in %.1fs", name, time.perf_counter() - started)
        return payload
    except (EdgarConfigError, ValueError) as exc:
        logging.info("%s error in %.1fs: %s", name, time.perf_counter() - started, type(exc).__name__)
        return _fail(exc)
    except Exception as exc:
        logging.exception("%s failed in %.1fs", name, time.perf_counter() - started)
        return _fail(exc)


@mcp.tool()
def get_trading_symbols(
    ticker_or_cik: str,
    accession: str | None = None,
    form: str = "10-K",
) -> dict:
    """Every dei:TradingSymbol fact on a 10-K or 10-Q, plus the legacy entity_info ticker scalar.

    Use this when you need the common stock ticker versus preferred, notes, or dual-class symbols.
    ticker_or_cik: ticker like NVDA or a CIK.
    accession: optional filing accession; default is the latest of `form`.
    form: 10-K (default) or 10-Q.
    """
    return _run_tool(
        "get_trading_symbols",
        trading_symbols,
        ticker_or_cik=ticker_or_cik,
        accession=accession,
        form=form,
    )


@mcp.tool()
def get_segment_revenue(
    ticker_or_cik: str,
    accession: str | None = None,
    form: str = "10-K",
) -> dict:
    """Dimensioned XBRL revenue facts from a 10-K or 10-Q (product, business, geographic axes).

    This is filing data, not a consolidated income statement.
    ticker_or_cik: ticker like NVDA or a CIK.
    accession: optional filing accession; default is the latest of `form`.
    form: 10-K (default) or 10-Q.
    """
    return _run_tool(
        "get_segment_revenue",
        segment_revenue,
        ticker_or_cik=ticker_or_cik,
        accession=accession,
        form=form,
    )


@mcp.tool()
def get_bdc_nonaccrual(
    ticker_or_cik: str,
    accession: str | None = None,
    form: str = "10-K",
) -> dict:
    """Non-accrual investments from a BDC 10-K or 10-Q, cited to the filing.

    Use this instead of guessing private-credit quality. ticker_or_cik must be
    an SEC BDC (814- filer) such as ARCC. Operating companies like NVDA raise.
    Non-accrual is the filer's tagged status, not Fitch PCDR and not PIK.
    """
    return _run_tool(
        "get_bdc_nonaccrual",
        bdc_nonaccrual,
        ticker_or_cik=ticker_or_cik,
        accession=accession,
        form=form,
    )


@mcp.tool()
def get_form4(ticker_or_cik: str, limit: int = 8) -> dict:
    """Recent Form 4 insider filings: who, role, activity, and transaction lines.

    limit: 1-20 filings, newest first. P/S are open_market true; A/M/F are false.
    """
    return _run_tool("get_form4", form4_filings, ticker_or_cik=ticker_or_cik, limit=limit)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
