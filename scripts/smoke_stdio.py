"""Prove the MCP stdio handshake. No live EDGAR. Stdlib only.

Default: <this python> -m edgar_mcp
Override: python scripts/smoke_stdio.py -- uvx --from . edgar-filings-mcp
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from queue import Empty, Queue

EXPECTED_TOOLS = [
    "get_trading_symbols",
    "get_segment_revenue",
    "get_bdc_nonaccrual",
    "get_form4",
]


def _reader(stream, queue: Queue) -> None:
    try:
        for line in stream:
            queue.put(line)
    finally:
        queue.put(None)


def _send(proc: subprocess.Popen, obj: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def _read_json(queue: Queue, timeout: float, proc: subprocess.Popen, stderr_q: Queue) -> dict:
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


def smoke(command: Sequence[str], init_timeout: float = 60.0) -> int:
    env = os.environ.copy()
    env.pop("EDGAR_IDENTITY", None)
    started = time.perf_counter()
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
                    "clientInfo": {"name": "edgar-mcp-smoke", "version": "0"},
                },
            },
        )
        init = _read_json(out_q, init_timeout, proc, err_q)
        init_sec = time.perf_counter() - started
        server = (init.get("result") or {}).get("serverInfo") or {}
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        listed = _read_json(out_q, 15.0, proc, err_q)
        names = [row.get("name") for row in ((listed.get("result") or {}).get("tools") or [])]
        print(f"command={list(command)}")
        print(f"initialize_sec={init_sec:.3f}")
        print(f"serverInfo={server}")
        print(f"tools={names}")
        if names != EXPECTED_TOOLS:
            print(f"FAIL expected {EXPECTED_TOOLS}", file=sys.stderr)
            return 1
        if server.get("name") != "edgar-filings":
            print(f"FAIL server name {server.get('name')}", file=sys.stderr)
            return 1
        print("SMOKE_OK")
        return 0
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        err = _drain(err_q)
        if err:
            print(err.rstrip(), file=sys.stderr)


def main(argv: list[str]) -> int:
    if "--" in argv:
        command = argv[argv.index("--") + 1 :]
        if not command:
            print("nothing after --", file=sys.stderr)
            return 2
    else:
        command = [sys.executable, "-m", "edgar_mcp"]
    return smoke(command)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
