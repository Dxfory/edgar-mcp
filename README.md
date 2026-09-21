# EDGAR Filings MCP

<!-- mcp-name: io.github.Dxfory/edgar-mcp -->

[![PyPI](https://img.shields.io/pypi/v/edgar-filings-mcp)](https://pypi.org/project/edgar-filings-mcp/)

Cursor / Claude tools that return **SEC filing numbers**, not web-search guesses.

**Who this is for:** people already in an IDE chat who need a ticker’s 10-K/10-Q symbols, segment revenue, BDC non-accrual, or Form 4 lines without writing edgartools glue.

**Pain it solves:** models invent segment mix, insider trades, and BDC credit quality. These tools return accession, concept, period, `open_market`, non-accrual method, and the EDGAR index URL so you can check the filing.

**What it is not:** a research product, a document reader, or a substitute for reading the 10-K. It wraps [edgartools](https://github.com/dgunning/edgartools) for four jobs only. China PE, humanoid robots, and unlisted credit CVs are out of scope — those filings are not on EDGAR.

## Install

Three lines:

1. Install `uv` ([docs](https://docs.astral.sh/uv/getting-started/installation/)).
2. Set `EDGAR_IDENTITY` to a name and a real email ([SEC FAQ](https://www.sec.gov/os/webmaster-faq#code-support)).
3. Paste `examples/cursor.mcp.json` into the client config.

```text
EDGAR_IDENTITY=Your Name you@example.com
```

macOS / Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

Then copy `examples/cursor.mcp.json` to `~/.cursor/mcp.json` (Windows: `%USERPROFILE%\.cursor\mcp.json`). Copy `examples/claude.mcp.json` into Claude Desktop’s MCP config.

Pin `mcp>=1.9,<2`. MCP 2.x renamed FastMCP. The package already pins that range.

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

PyPI package `edgar-filings-mcp` is live. Registry name is `io.github.Dxfory/edgar-mcp`. Skip Smithery hosted.

From git instead of PyPI:

```bash
uvx --from git+https://github.com/Dxfory/edgar-mcp.git edgar-filings-mcp
```

The first `uvx` launch downloads edgartools (pandas / pyarrow). If the client looks stuck, run the same command once in a terminal so uv can cache the wheels, then restart the MCP server. After that, initialize is a couple of seconds.

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

`form` on the first three tools is `10-K` (default) or `10-Q`. `get_bdc_nonaccrual` only accepts SEC BDCs (814- filers) such as `ARCC`. There is no fifth tool.

## Hot-theme footguns this server will / will not answer

| Theme | Agent invents | Tool | Stop |
| --- | --- | --- | --- |
| AI infrastructure | NVIDIA / hyperscaler “AI mix” | `get_segment_revenue` on `NVDA` (Data Center is tagged). AMZN/MSFT capex is **not** AI-only | Do not add a fake AI-capex tool |
| Private credit / BDC | Non-accrual, NAV as credit quality, PIK as current | `get_bdc_nonaccrual` | Non-accrual ≠ Fitch default rate; PIK can still be accrual |
| GP-led continuation vehicles | Deal price and “premium to par” | None | Private secondaries are not EDGAR |
| China PE / 具身智能 | Round sizes and factory hours | None | SSE/HKEX, not EDGAR |

## Footguns the tools already warn about

- `entity_info.ticker` is last-wins on repeated `TradingSymbol` facts. Dual-class and preferred tickers can replace the common symbol.
- Segment mix is **not** in `get_financials()`. Some statement “DETAILED” views drop reportable-segment lines; this server queries dimensioned facts instead.
- Form 4 `A` / `M` / `F` are grants, option exercises, and tax withholding — `open_market` is false.
- BDC `extraction_method=none` or a zero rate plus extractor warnings is a parse gap, not proof the book is clean.
- Latest `10-K` can be a `10-K/A`. The tools prefer the original form so Schedule-of-Investments footnotes are not dropped.

## Run without Cursor

```bash
python -m edgar_mcp
```

stdio only. Do not print to stdout.

```bash
python tests/run_offline.py
python scripts/smoke_stdio.py
python scripts/pressure.py
```

`smoke_stdio.py` only checks initialize + four tool names (no EDGAR). After `uvx` is on PATH:

```bash
python scripts/smoke_stdio.py -- uvx edgar-filings-mcp
```

`pressure.py` hits live EDGAR and needs `EDGAR_IDENTITY`.

## License

MIT. Filing data is from the SEC EDGAR system; this project is not affiliated with the SEC.
