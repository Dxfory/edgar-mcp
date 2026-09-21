"""MCP server: BDC loan look-through from a cited Schedule of Investments snapshot."""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

from bdc_lookthrough import __version__
from bdc_lookthrough.snapshot import load_snapshot

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s")

mcp = FastMCP(
    "bdc-lookthrough",
    instructions=(
        "Look through publicly traded BDCs' Schedules of Investments. "
        "Answer which BDC holds a private borrower, named non-accrual, and whether the SOI total "
        "reconciles to the balance-sheet Investments-at-FV line. "
        "Always cite accession_number and index_url. "
        "Default data is a dated snapshot of ARCC, BXSL, and OBDC — not a live feed. "
        "Do not invent loan overlap, non-accrual rates, or private-credit quality. "
        "Name matching is not a CUSIP. reconcile_ok=false means do not treat SOI row sums as NAV."
    ),
)
mcp._mcp_server.version = __version__


def _fail(exc: Exception) -> dict:
    return {"error": f"{type(exc).__name__}: {exc}"}


def _run(name: str, fn: Callable[..., dict], **kwargs: Any) -> dict:
    started = time.perf_counter()
    logging.info("%s start %s", name, {k: v for k, v in kwargs.items() if v is not None})
    try:
        payload = fn(**kwargs)
        logging.info("%s ok in %.1fs", name, time.perf_counter() - started)
        return payload
    except ValueError as exc:
        logging.info("%s error in %.1fs: %s", name, time.perf_counter() - started, type(exc).__name__)
        return _fail(exc)
    except Exception as exc:
        logging.exception("%s failed in %.1fs", name, time.perf_counter() - started)
        return _fail(exc)


@mcp.tool()
def get_soi(ticker: str, limit: int = 25, debt_only: bool = False) -> dict:
    """Holdings from a BDC Schedule of Investments in the snapshot, cited to the 10-Q/10-K.

    ticker: ARCC, BXSL, or OBDC in v1. limit: 1-200 rows, largest |fair_value| first.
    """
    snap = load_snapshot()
    return _run("get_soi", snap.soi, ticker=ticker, limit=limit, debt_only=debt_only)


@mcp.tool()
def loan_overlap(borrower: str, limit: int = 40) -> dict:
    """Which snapshot BDCs disclose a loan or equity stake in this private borrower.

    borrower: legal name, d/b/a, or f/k/a (for example Auctane or Stamps.com).
    Returns tickers, fair value, accession, and index_url. Name match is not a CUSIP.
    """
    snap = load_snapshot()
    return _run("loan_overlap", snap.overlap, query=borrower, limit=limit)


@mcp.tool()
def nonaccrual_names(ticker: str | None = None) -> dict:
    """Named non-accrual investments from the snapshot, with extraction_method.

    ticker: optional ARCC / BXSL / OBDC. Omit to list all three. Non-accrual is not a default rate.
    """
    snap = load_snapshot()
    return _run("nonaccrual_names", snap.nonaccrual_names, ticker=ticker)


@mcp.tool()
def reconcile_to_bs(ticker: str) -> dict:
    """Compare SOI row-sum fair value to us-gaap:InvestmentOwnedAtFairValue on the balance sheet.

    ticker: ARCC, BXSL, or OBDC. reconcile_ok is false when XBRL rollups inflate the SOI sum.
    """
    snap = load_snapshot()
    return _run("reconcile_to_bs", snap.reconcile, ticker=ticker)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
