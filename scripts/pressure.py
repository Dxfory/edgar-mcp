"""Live EDGAR pressure test. Requires EDGAR_IDENTITY. Not run in CI."""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _ok(name: str, cond: bool, detail: str) -> bool:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}: {detail}")
    return cond


def main() -> int:
    _load_dotenv()
    from edgar_mcp.filings import (
        EdgarConfigError,
        form4_filings,
        normalize_form,
        segment_revenue,
        trading_symbols,
        warmup,
    )

    passed = 0
    failed = 0

    def check(name: str, cond: bool, detail: str) -> None:
        nonlocal passed, failed
        if _ok(name, cond, detail):
            passed += 1
        else:
            failed += 1

    try:
        normalize_form("8-K")
        check("reject 8-K", False, "should have raised")
    except ValueError as exc:
        check("reject 8-K", "10-Q" in str(exc), str(exc))

    try:
        warmup()
        check("warmup", True, "ticker cache loaded")
    except EdgarConfigError as exc:
        print(f"SKIP live cases: {exc}")
        print(f"{passed} passed, {failed} failed, live skipped")
        return 1 if failed else 0
    except Exception as exc:
        check("warmup", False, f"{type(exc).__name__}: {exc}")
        print(f"{passed} passed, {failed} failed")
        return 1

    cases = [
        ("NVDA", "10-K", True, True, True),
        ("NVDA", "10-Q", True, True, False),
        ("AAPL", "10-K", True, True, False),
        ("MSFT", "10-K", True, False, False),
        ("GOOGL", "10-K", True, False, False),
        ("JPM", "10-K", True, False, False),
        ("TSM", "10-K", False, False, False),
        ("ZZZNOPE123", "10-K", False, False, False),
    ]

    for ticker, form, expect_symbols, expect_segments, expect_form4 in cases:
        time.sleep(0.35)
        try:
            out = trading_symbols(ticker, form=form)
            src = out.get("source") or {}
            symbols = [row["symbol"] for row in out.get("trading_symbols") or []]
            has_cite = bool(src.get("accession_number") and src.get("index_url"))
            if expect_symbols:
                check(
                    f"{ticker} {form} symbols",
                    bool(symbols) and has_cite and "error" not in out,
                    f"symbols={symbols[:6]} accession={src.get('accession_number')}",
                )
            else:
                check(f"{ticker} {form} symbols unexpected success", False, str(src)[:200])
        except Exception as exc:
            check(
                f"{ticker} {form} symbols",
                not expect_symbols,
                f"{type(exc).__name__}: {exc}",
            )
            if expect_symbols:
                traceback.print_exc()

        if expect_segments:
            time.sleep(0.2)
            try:
                out = segment_revenue(ticker, form=form)
                rows = out.get("segments") or []
                src = out.get("source") or {}
                check(
                    f"{ticker} {form} segments",
                    len(rows) > 0 and bool(src.get("index_url")),
                    f"n={len(rows)} first={rows[0].get('label') or rows[0].get('axis') if rows else None}",
                )
            except Exception as exc:
                check(f"{ticker} {form} segments", False, f"{type(exc).__name__}: {exc}")
                traceback.print_exc()

        if expect_form4:
            time.sleep(0.2)
            try:
                out = form4_filings(ticker, limit=5)
                filings = out.get("filings") or []
                f_ok = True
                f_n = 0
                for filing in filings:
                    for row in filing.get("transactions") or []:
                        if row.get("code") == "F":
                            f_n += 1
                            if row.get("open_market") is not False:
                                f_ok = False
                check(
                    f"{ticker} form4",
                    out.get("count", 0) >= 1 and f_ok,
                    f"count={out.get('count')} codes={out.get('code_counts')} F_rows={f_n}",
                )
            except Exception as exc:
                check(f"{ticker} form4", False, f"{type(exc).__name__}: {exc}")
                traceback.print_exc()

    print(f"{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
