# EDGAR Filings MCP

<!-- mcp-name: io.github.Dxfory/edgar-mcp -->

[![PyPI](https://img.shields.io/pypi/v/edgar-filings-mcp)](https://pypi.org/project/edgar-filings-mcp/1.1.3/)
[![MCP](https://img.shields.io/badge/MCP-io.github.Dxfory%2Fedgar--mcp-555)](https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.Dxfory/edgar-mcp)
[![test](https://github.com/Dxfory/edgar-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/Dxfory/edgar-mcp/actions/workflows/test.yml)

Cursor / Claude tools that return **SEC filing numbers** with accession, concept, period and EDGAR URL.

**Who this is for:** people already in an IDE chat who need a ticker’s 10-K/10-Q symbols, segment revenue, BDC non-accrual, or Form 4 lines without writing edgartools glue.

**Pain it solves:** models invent segment mix, insider trades, and BDC credit quality. These tools return accession, concept, period, `open_market`, non-accrual method, and the EDGAR index URL so you can check the filing.

**Scope:** four focused jobs on top of [edgartools](https://github.com/dgunning/edgartools) — symbols, segment revenue, BDC non-accrual, Form 4 — each returning accession, concept, period and the EDGAR index URL so every number is checkable.

## Install

If `uv` is already on PATH, paste this into `~/.cursor/mcp.json` (Windows: `%USERPROFILE%\.cursor\mcp.json`). Use a real name and email ([SEC FAQ](https://www.sec.gov/os/webmaster-faq#code-support)). Same snippet is in `examples/cursor.mcp.json` and `examples/claude.mcp.json`.

```json
{
  "mcpServers": {
    "edgar-filings": {
      "command": "uvx",
      "args": ["edgar-filings-mcp"],
      "env": {
        "EDGAR_IDENTITY": "Your Name you@example.com"
      }
    }
  }
}
```

PyPI package `edgar-filings-mcp` is live. Registry name is `io.github.Dxfory/edgar-mcp`. Skip Smithery hosted. Pin `mcp>=1.9,<2` — MCP 2.x renamed FastMCP; the package already pins that range.

The first `uvx` launch downloads edgartools (pandas / pyarrow). If the client looks stuck, run `uvx edgar-filings-mcp` once in a terminal so uv can cache the wheels, then restart the MCP server. After that, initialize is a couple of seconds.

No `uv` yet:

macOS / Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

From git instead of PyPI:

```bash
uvx --from git+https://github.com/Dxfory/edgar-mcp.git edgar-filings-mcp
```

### Clone (no uv)

```bash
git clone https://github.com/Dxfory/edgar-mcp.git
cd edgar-mcp
python -m venv .venv
```

macOS / Linux:

```bash
.venv/bin/python -m pip install -e .
```

Windows:

```text
.\.venv\Scripts\python -m pip install -e .
```

Point the client at that interpreter with args `["-m", "edgar_mcp"]`.

If PyPI SSL fails (common with a local HTTPS proxy), use a mirror:

```bash
python -m pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## Tools

| Tool | Returns |
| --- | --- |
| `get_trading_symbols` | Every `dei:TradingSymbol` on the latest 10-K or 10-Q, plus the legacy `entity_info` scalar |
| `get_segment_revenue` | Dimensioned XBRL revenue (product / business / geographic axes) |
| `get_bdc_nonaccrual` | BDC non-accrual rate, fair value, named investments, and extraction method |
| `get_form4` | Newest Form 4 summaries, transaction lines, `open_market`, and `code_counts` |

`form` on `get_trading_symbols`, `get_segment_revenue`, and `get_bdc_nonaccrual` is `10-K` (default) or `10-Q`. `get_bdc_nonaccrual` accepts SEC BDCs (814- filers) such as `ARCC`.

## Theme coverage

Four tools: trading symbols, segment revenue, BDC non-accrual, Form 4. Each figure carries accession, concept, period, and an EDGAR URL. NVDA segment revenue resolves through `get_segment_revenue`. BDC credit work resolves through `get_bdc_nonaccrual`. The server speaks stdio.

| Theme | Filing figure | Tool |
| --- | --- | --- |
| Listed symbols | Every `dei:TradingSymbol` on the latest 10-K or 10-Q | `get_trading_symbols` |
| AI infrastructure | NVDA Data Center segment revenue, tagged on the filing | `get_segment_revenue` on `NVDA` |
| Private credit / BDC | Non-accrual rate, fair value, named investments, extraction method | `get_bdc_nonaccrual` |
| Insider filings | Newest Form 4 summaries, transaction lines, `open_market`, and `code_counts` | `get_form4` |

## Footguns the tools already warn about

- `entity_info.ticker` is last-wins on repeated `TradingSymbol` facts. Dual-class and preferred tickers can replace the common symbol.
- Segment mix comes from dimensioned facts on this server. Statement “DETAILED” views can drop reportable-segment lines; `get_financials()` is a separate surface.
- Form 4 `A` / `M` / `F` are grants, option exercises, and tax withholding — `open_market` is false.
- BDC `extraction_method=none` or a zero rate plus extractor warnings marks a parse gap — read the Schedule of Investments in the filing for that BDC.
- Latest `10-K` can be a `10-K/A`. The tools prefer the original form so Schedule-of-Investments footnotes stay in the extract.

## Run without Cursor

```bash
python -m edgar_mcp
```

The server speaks stdio. Keep logs off stdout so the MCP stream stays the tool protocol.

```bash
python tests/run_offline.py
python scripts/smoke_stdio.py
python scripts/pressure.py
```

`smoke_stdio.py` checks initialize plus the four tool names. Live EDGAR calls belong to `pressure.py`. After `uvx` is on PATH:

```bash
python scripts/smoke_stdio.py -- uvx edgar-filings-mcp
```

`pressure.py` hits live EDGAR and needs `EDGAR_IDENTITY`.

## License

MIT. Filing data is from the SEC EDGAR system; this project is not affiliated with the SEC.
