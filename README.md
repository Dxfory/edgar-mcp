# EDGAR Filings MCP

<!-- mcp-name: io.github.Dxfory/edgar-mcp -->

Cursor / Claude tools that return **SEC filing numbers**, not web-search guesses.

**Who this is for:** people already in an IDE chat who need a ticker’s 10-K/10-Q symbols, segment revenue, or Form 4 lines without writing edgartools glue.

**Pain it solves:** models invent segment mix and insider trades. These tools return accession, concept, period, `open_market`, and the EDGAR index URL so you can check the filing.

**What it is not:** a research product, a document reader, or a substitute for reading the 10-K. It wraps [edgartools](https://github.com/dgunning/edgartools) for three jobs only.

## Install

SEC fair-access needs a User-Agent with a **name and a real email** ([SEC FAQ](https://www.sec.gov/os/webmaster-faq#code-support)):

```text
EDGAR_IDENTITY=Your Name you@example.com
```

Pin `mcp>=1.9,<2`. MCP 2.x renamed FastMCP.

### Cursor / Claude Desktop (`uv`)

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

Copy `examples/cursor.mcp.json` into `~/.cursor/mcp.json` (Windows: `%USERPROFILE%\.cursor\mcp.json`). Copy `examples/claude.mcp.json` into Claude Desktop’s MCP config.

### Clone

```bash
git clone https://github.com/Dxfory/edgar-mcp.git
cd edgar-mcp
python -m venv .venv
```

Windows: `.\.venv\Scripts\python -m pip install -e .`  
macOS/Linux: `.venv/bin/python -m pip install -e .`

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
| `get_form4` | Newest Form 4 summaries, transaction lines, `open_market`, and `code_counts` |

`form` on the first two tools is `10-K` (default) or `10-Q`.

## Footguns the tools already warn about

- `entity_info.ticker` is last-wins on repeated `TradingSymbol` facts. Dual-class and preferred tickers can replace the common symbol.
- Segment mix is **not** in `get_financials()`. Some statement “DETAILED” views drop reportable-segment lines; this server queries dimensioned facts instead.
- Form 4 `A` / `M` / `F` are grants, option exercises, and tax withholding — `open_market` is false.

## Run without Cursor

```bash
python -m edgar_mcp
```

stdio only. Do not print to stdout.

```bash
python tests/run_offline.py
python scripts/pressure.py
```

`pressure.py` hits live EDGAR and needs `EDGAR_IDENTITY`.

## License

MIT. Filing data is from the SEC EDGAR system; this project is not affiliated with the SEC.
