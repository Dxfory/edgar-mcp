"""Pressure-test the bundled snapshot, CLI contract, and MCP tools.

Default: offline only (safe for CI, no SEC traffic).
Live citation GETs: ``--live`` with ``EDGAR_IDENTITY`` (polite, few requests).
Full SOI refresh: ``--live-refresh`` (slow; optional).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
from collections.abc import Sequence
from pathlib import Path
from queue import Empty, Queue
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

GENERIC_QUERIES = (
    "group",
    "parent",
    "software",
    "health",
    "capital",
    "acquisition",
    "international",
    "management",
    "holdings",
)
KNOWN_HITS = {
    "Auctane": {"ARCC", "BXSL", "OBDC"},
    "Anaplan": {"ARCC", "BXSL", "OBDC"},
    "Stamps.com": {"OBDC"},
    "Guidehouse": {"BXSL", "OBDC"},
    "PetVet": {"ARCC", "OBDC"},
}


def _ok(name: str, cond: bool, detail: str) -> bool:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}: {detail}")
    return cond


class _Counter:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, name: str, cond: bool, detail: str) -> None:
        if _ok(name, cond, detail):
            self.passed += 1
        else:
            self.failed += 1


def _load_dotenv() -> None:
    for path in (ROOT / ".env", ROOT.parent / ".env"):
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def _reader(stream, queue: Queue) -> None:
    try:
        for line in stream:
            queue.put(line)
    finally:
        queue.put(None)


def _send(proc, obj: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def _drain(queue: Queue) -> str:
    chunks: list[str] = []
    while True:
        try:
            item = queue.get_nowait()
        except Empty:
            break
        if item:
            chunks.append(item)
    return "".join(chunks)


def _read_json(queue: Queue, timeout: float, proc, stderr_q: Queue) -> dict:
    deadline = time.time() + timeout
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            err = _drain(stderr_q)
            raise TimeoutError(f"no JSON-RPC line in {timeout:.0f}s stderr={err[-2000:]}")
        try:
            line = queue.get(timeout=remaining)
        except Empty:
            continue
        if line is None:
            err = _drain(stderr_q)
            raise RuntimeError(f"server stdout closed rc={proc.poll()} stderr={err[-2000:]}")
        text = line.strip()
        if not text:
            continue
        return json.loads(text)


def _mcp_session(command: Sequence[str], ctr: _Counter) -> None:
    import subprocess

    env = os.environ.copy()
    env.pop("EDGAR_IDENTITY", None)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen(
        list(command),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )
    out_q: Queue = Queue()
    err_q: Queue = Queue()
    threading.Thread(target=_reader, args=(proc.stdout, out_q), daemon=True).start()
    threading.Thread(target=_reader, args=(proc.stderr, err_q), daemon=True).start()
    try:
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "bdc-lookthrough-pressure", "version": "0"},
                },
            },
        )
        init = _read_json(out_q, 60.0, proc, err_q)
        server = (init.get("result") or {}).get("serverInfo") or {}
        ctr.check("mcp initialize", server.get("name") == "bdc-lookthrough", str(server))
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        calls = [
            ("get_soi", {"ticker": "ARCC", "limit": 3}),
            ("loan_overlap", {"borrower": "Auctane"}),
            ("nonaccrual_names", {"ticker": "BXSL"}),
            ("reconcile_to_bs", {"ticker": "OBDC"}),
            ("get_soi", {"ticker": "NVDA"}),
            ("loan_overlap", {"borrower": "ab"}),
            ("loan_overlap", {"borrower": "group"}),
        ]
        for idx, (name, arguments) in enumerate(calls, start=2):
            _send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": idx,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                },
            )
            reply = _read_json(out_q, 20.0, proc, err_q)
            result = reply.get("result") or {}
            content = result.get("content") or []
            text = ""
            if content and isinstance(content[0], dict):
                text = str(content[0].get("text") or "")
            payload = {}
            try:
                payload = json.loads(text) if text else {}
            except json.JSONDecodeError:
                payload = {"raw": text[:300]}
            is_error = bool(result.get("isError")) or "error" in payload
            if name == "get_soi" and arguments.get("ticker") == "NVDA":
                ctr.check("mcp NVDA rejected", is_error or "error" in payload, str(payload)[:180])
            elif name == "loan_overlap" and arguments.get("borrower") == "ab":
                ctr.check("mcp short query rejected", is_error or "error" in payload, str(payload)[:180])
            elif name == "loan_overlap" and arguments.get("borrower") == "group":
                npos = int(payload.get("n_positions") or 0)
                ctr.check("mcp generic group empty", (not is_error) and npos == 0, f"n_positions={npos}")
            elif name == "loan_overlap":
                tickers = set(payload.get("tickers") or [])
                ctr.check(
                    "mcp Auctane overlap",
                    tickers == {"ARCC", "BXSL", "OBDC"} and bool(payload.get("sources")),
                    f"tickers={sorted(tickers)} n={payload.get('n_positions')}",
                )
            elif name == "get_soi":
                ctr.check(
                    "mcp ARCC soi",
                    payload.get("n_returned") == 3 and bool((payload.get("source") or {}).get("index_url")),
                    f"n_returned={payload.get('n_returned')}",
                )
            elif name == "nonaccrual_names":
                ctr.check(
                    "mcp BXSL nonaccrual",
                    payload.get("count", 0) >= 1 and bool(payload.get("blocks")),
                    f"count={payload.get('count')}",
                )
            else:
                ctr.check(
                    "mcp OBDC reconcile",
                    "reconcile_ok" in payload and payload.get("bs_fair_value") is not None,
                    f"ok={payload.get('reconcile_ok')} err={payload.get('reconcile_error_pct')}",
                )
    except Exception as exc:
        ctr.check("mcp session", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
            proc.wait(timeout=5)


def _offline(ctr: _Counter) -> None:
    from bdc_lookthrough.names import is_junk_borrower
    from bdc_lookthrough.snapshot import load_snapshot, reset_snapshot_cache

    reset_snapshot_cache()
    snap = load_snapshot()
    tickers = {item["ticker"] for item in snap.universe}
    ctr.check("universe", tickers == {"ARCC", "BXSL", "OBDC"}, str(sorted(tickers)))
    ctr.check("holdings loaded", len(snap.holdings) > 500, f"n={len(snap.holdings)}")

    for ticker in ("ARCC", "BXSL", "OBDC"):
        soi = snap.soi(ticker, limit=8)
        rec = snap.reconcile(ticker)
        na = snap.nonaccrual_names(ticker)
        src = soi.get("source") or {}
        ctr.check(
            f"{ticker} soi cited",
            soi.get("n_returned") == 8
            and bool(src.get("accession_number"))
            and str(src.get("index_url") or "").startswith("https://www.sec.gov/"),
            f"n_holdings={soi.get('n_holdings')} acc={src.get('accession_number')}",
        )
        json.dumps(soi)
        json.dumps(rec)
        json.dumps(na)
        ctr.check(
            f"{ticker} reconcile numbers",
            rec.get("bs_fair_value") not in (None, 0) and rec.get("soi_sum_fair_value", 0) > 0,
            f"ok={rec.get('reconcile_ok')} soi={rec.get('soi_sum_fair_value')} bs={rec.get('bs_fair_value')}",
        )
        ctr.check(
            f"{ticker} nonaccrual method",
            bool(na.get("blocks")) and na["blocks"][0].get("extraction_method") in {"footnote", "custom_concept", "aggregate_concept", "none"},
            f"method={na['blocks'][0].get('extraction_method')} count={na.get('count')}",
        )

    bxsl = snap.reconcile("BXSL")
    ctr.check("BXSL within 3%", bool(bxsl.get("reconcile_ok")), f"err={bxsl.get('reconcile_error_pct')}")
    arcc = snap.reconcile("ARCC")
    ctr.check("ARCC gap reported", bxsl.get("reconcile_ok") is True and arcc.get("reconcile_ok") is False, f"ARCC err={arcc.get('reconcile_error_pct')}")

    for query, expect in KNOWN_HITS.items():
        hit = snap.overlap(query)
        got = set(hit.get("tickers") or [])
        ctr.check(
            f"overlap {query}",
            expect.issubset(got) and all(src.get("index_url") for src in hit.get("sources") or []),
            f"tickers={sorted(got)} fv={hit.get('total_fair_value')}",
        )

    for query in GENERIC_QUERIES:
        hit = snap.overlap(query)
        ctr.check(
            f"generic {query!r} empty",
            hit.get("n_positions") == 0 and hit.get("bdc_count") == 0,
            f"n={hit.get('n_positions')} keys={hit.get('borrower_keys')}",
        )

    miss = 0
    checked = 0
    seen: set[str] = set()
    t0 = time.perf_counter()
    for row in snap.holdings:
        norm = str(row.get("borrower_norm") or "")
        if not norm or is_junk_borrower(norm) or norm in seen:
            continue
        seen.add(norm)
        checked += 1
        hit = snap.overlap(norm)
        got = set(hit.get("tickers") or [])
        if row.get("ticker") not in got:
            miss += 1
            if miss <= 5:
                print(f"  self-hit miss {norm!r} ticker={row.get('ticker')} got={sorted(got)}")
    elapsed = time.perf_counter() - t0
    ctr.check("self-hit all names", miss == 0 and checked > 200, f"checked={checked} miss={miss} sec={elapsed:.2f}")

    try:
        snap.soi("ARCC", limit=0)
        ctr.check("limit 0 rejected", False, "should have raised")
    except ValueError as exc:
        ctr.check("limit 0 rejected", "1 to 200" in str(exc), str(exc))

    try:
        snap.soi("NVDA")
        ctr.check("NVDA rejected", False, "should have raised")
    except ValueError as exc:
        ctr.check("NVDA rejected", "Unknown BDC" in str(exc), str(exc)[:160])

    blank = snap.nonaccrual_names("  ")
    ctr.check("blank ticker is all names", blank.get("count", 0) > 0 and len(blank.get("blocks") or []) == 3, f"count={blank.get('count')}")

    t1 = time.perf_counter()
    for _ in range(80):
        snap.overlap("Auctane")
        snap.reconcile("BXSL")
    repeat_sec = time.perf_counter() - t1
    ctr.check("repeat 80 overlap+reconcile", repeat_sec < 5.0, f"sec={repeat_sec:.2f}")


def _live_citations(ctr: _Counter) -> None:
    from bdc_lookthrough.edgar import EdgarConfigError, ensure_identity
    from bdc_lookthrough.snapshot import load_snapshot

    try:
        ident = ensure_identity()
    except EdgarConfigError as exc:
        print(f"SKIP live citations: {exc}")
        return
    snap = load_snapshot()
    ua = ident.encode("ascii", errors="replace").decode("ascii")
    for item in snap.universe:
        url = item.get("index_url")
        ticker = item.get("ticker")
        time.sleep(0.4)
        try:
            req = Request(url, headers={"User-Agent": ua, "Accept-Encoding": "identity"})
            with urlopen(req, timeout=30) as resp:
                status = getattr(resp, "status", 200)
                body = resp.read(200)
            ctr.check(
                f"{ticker} index_url",
                status == 200,
                f"status={status} url={url}",
            )
        except (HTTPError, URLError, TimeoutError) as exc:
            ctr.check(f"{ticker} index_url", False, f"{type(exc).__name__}: {exc}")


def _live_refresh(ctr: _Counter) -> None:
    from bdc_lookthrough.edgar import EdgarConfigError, refresh_snapshot
    from bdc_lookthrough.snapshot import Snapshot

    try:
        payload = refresh_snapshot(("ARCC", "BXSL", "OBDC"))
    except EdgarConfigError as exc:
        print(f"SKIP live refresh: {exc}")
        return
    except Exception as exc:
        ctr.check("live refresh", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
        return
    live = Snapshot(payload, data_mode="live_edgar")
    ctr.check("live universe", {row["ticker"] for row in live.universe} == {"ARCC", "BXSL", "OBDC"}, str(live.universe))
    hit = live.overlap("Auctane")
    ctr.check(
        "live Auctane cited",
        hit.get("bdc_count", 0) >= 1 and all(src.get("accession_number") for src in hit.get("sources") or []),
        f"tickers={hit.get('tickers')} n={hit.get('n_positions')}",
    )
    rec = live.reconcile("BXSL")
    ctr.check("live BXSL has BS line", rec.get("bs_fair_value") not in (None, 0), f"ok={rec.get('reconcile_ok')} err={rec.get('reconcile_error_pct')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pressure-test bdc-lookthrough")
    parser.add_argument("--live", action="store_true", help="GET snapshot index URLs from SEC (needs EDGAR_IDENTITY)")
    parser.add_argument("--live-refresh", action="store_true", help="Rebuild SOI from live EDGAR (slow)")
    parser.add_argument(
        "--mcp-cmd",
        nargs="+",
        default=[sys.executable, "-m", "bdc_lookthrough.server"],
        help="MCP stdio command",
    )
    args = parser.parse_args(argv)
    _load_dotenv()
    ctr = _Counter()
    _offline(ctr)
    _mcp_session(args.mcp_cmd, ctr)
    if args.live or args.live_refresh:
        _live_citations(ctr)
    if args.live_refresh:
        _live_refresh(ctr)
    print(f"{ctr.passed} passed, {ctr.failed} failed")
    return 1 if ctr.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
