"""MCP server: SEC 10-K/10-Q symbols, segment revenue, Form 4."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP

from edgar_mcp.filings import (
    EdgarConfigError,
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
        "Do not invent segment mix or insider trades. "
        "entity_info_ticker can be the wrong class on multi-security filings; prefer trading_symbols. "
        "Form 4 A/M/F are not open-market trades; trust open_market=false."
    ),
    lifespan=_lifespan,
)


def _fail(exc: Exception) -> dict:
    return {"error": f"{type(exc).__name__}: {exc}"}


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
    try:
        return trading_symbols(ticker_or_cik, accession=accession, form=form)
    except (EdgarConfigError, ValueError) as exc:
        return _fail(exc)
    except Exception as exc:
        logging.exception("get_trading_symbols failed")
        return _fail(exc)


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
    try:
        return segment_revenue(ticker_or_cik, accession=accession, form=form)
    except (EdgarConfigError, ValueError) as exc:
        return _fail(exc)
    except Exception as exc:
        logging.exception("get_segment_revenue failed")
        return _fail(exc)


@mcp.tool()
def get_form4(ticker_or_cik: str, limit: int = 8) -> dict:
    """Recent Form 4 insider filings: who, role, activity, and transaction lines.

    limit: 1-20 filings, newest first. P/S are open_market true; A/M/F are false.
    """
    try:
        return form4_filings(ticker_or_cik, limit=limit)
    except (EdgarConfigError, ValueError) as exc:
        return _fail(exc)
    except Exception as exc:
        logging.exception("get_form4 failed")
        return _fail(exc)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
