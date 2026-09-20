# EDGAR Filings MCP

Cursor / Claude tools that return **SEC filing numbers**, not web-search guesses.

**Who this is for:** people already in an IDE chat who need a ticker’s 10-K symbols, segment revenue, or Form 4 lines without writing edgartools glue.

**Pain it solves:** models invent segment mix and insider trades. These tools return accession, concept, period, and the EDGAR index URL so you can check the filing.

**What it is not:** a research product, a document reader, or a substitute for reading the 10-K. It wraps [edgartools](https://github.com/dgunning/edgartools) for three jobs only.

## Install

SEC fair-access needs a User-Agent with a **name and a real email** ([SEC FAQ](https://www.sec.gov/os/webmaster-faq#code-support)):

```text
EDGAR_IDENTITY=Your Name you@example.com
```

### Cursor (uv)

Copy `examples/cursor.mcp.json` into `~/.cursor/mcp.json` (or project `.cursor/mcp.json`) and replace the email. That file runs:

```json
{
  "mcpServers": {
    "edgar-filings": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/Dxfory/edgar-mcp.git",
        "edgar-filings-mcp"
      ],
      "env": {
        "EDGAR_IDENTITY": "Your Name you@example.com"
      }
    }
  }
}
```

Pin `mcp>=1.9,<2`. MCP 2.x renamed FastMCP.

### Clone

```powershell
git clone https://github.com/Dxfory/edgar-mcp.git
cd edgar-mcp
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
```

Then point Cursor at `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` with args `["-m", "edgar_mcp"]`.

If PyPI SSL fails (common with a local proxy), install from a mirror:

```powershell
.\.venv\Scripts\python -m pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## Tools

| Tool | Returns |
| --- | --- |
| `get_trading_symbols` | Every `dei:TradingSymbol` on the latest 10-K, plus the legacy `entity_info` scalar |
| `get_segment_revenue` | Dimensioned XBRL revenue (product / business / geographic axes) |
| `get_form4` | Newest Form 4 summaries and transaction lines |

## Footguns the tools already warn about

- `entity_info.ticker` is last-wins on repeated `TradingSymbol` facts. Dual-class and preferred tickers can replace the common symbol.
- Segment mix is **not** in `get_financials()`. Some statement “DETAILED” views drop reportable-segment lines; this server queries dimensioned facts instead.
- Form 4 `A` / `M` / `F` are grants, option exercises, and tax withholding — not open-market buys.

## Run without Cursor

```powershell
.\.venv\Scripts\python -m edgar_mcp
```

stdio only. Do not print to stdout.

Offline tests (no network, no edgartools):

```powershell
.\.venv\Scripts\python tests\run_offline.py
```

## License

MIT. Filing data is from the SEC EDGAR system; this project is not affiliated with the SEC.
