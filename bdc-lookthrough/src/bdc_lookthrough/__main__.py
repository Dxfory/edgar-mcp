"""CLI: overlap / soi / nonaccrual / reconcile / refresh."""

from __future__ import annotations

import argparse
import json
import sys

from bdc_lookthrough.snapshot import load_snapshot


def _print(payload: dict) -> int:
    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 1 if payload.get("error") else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bdc-lookthrough",
        description="Look through BDC Schedules of Investments. Cite the filing.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    overlap = sub.add_parser("overlap", help="Which snapshot BDCs hold this borrower")
    overlap.add_argument("borrower")
    overlap.add_argument("--limit", type=int, default=40)

    soi = sub.add_parser("soi", help="Holdings for one BDC ticker")
    soi.add_argument("ticker")
    soi.add_argument("--limit", type=int, default=15)
    soi.add_argument("--debt-only", action="store_true")

    na = sub.add_parser("nonaccrual", help="Named non-accrual investments")
    na.add_argument("ticker", nargs="?", default=None)

    rec = sub.add_parser("reconcile", help="SOI sum vs balance-sheet Investments at FV")
    rec.add_argument("ticker")

    refresh = sub.add_parser("refresh", help="Rebuild snapshot from live EDGAR (needs edgartools + EDGAR_IDENTITY)")
    refresh.add_argument("--out", default="snapshot.json.gz")
    refresh.add_argument("--tickers", default="ARCC,BXSL,OBDC")

    mcp = sub.add_parser("mcp", help="Run the MCP stdio server")

    args = parser.parse_args(argv)
    if args.cmd == "mcp":
        from bdc_lookthrough.server import main as mcp_main

        mcp_main()
        return 0
    if args.cmd == "refresh":
        from bdc_lookthrough.edgar import refresh_snapshot, write_snapshot

        tickers = [part.strip() for part in args.tickers.split(",") if part.strip()]
        payload = refresh_snapshot(tickers)
        path = write_snapshot(payload, args.out)
        print(path)
        return 0

    snap = load_snapshot()
    if args.cmd == "overlap":
        return _print(snap.overlap(args.borrower, limit=args.limit))
    if args.cmd == "soi":
        return _print(snap.soi(args.ticker, limit=args.limit, debt_only=args.debt_only))
    if args.cmd == "nonaccrual":
        return _print(snap.nonaccrual_names(args.ticker))
    if args.cmd == "reconcile":
        return _print(snap.reconcile(args.ticker))
    parser.error(f"unknown command {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
