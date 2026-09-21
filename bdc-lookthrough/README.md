# BDC Lookthrough

Which publicly traded BDCs hold the same private borrower — from the **Schedule of Investments**, with a filing URL, not from a chat model’s memory.

```text
$ bdc-lookthrough overlap Auctane
tickers: ARCC, BXSL, OBDC
fair value: ~$543m across 3 positions
index: 0001628280-26-050307, 0001736035-26-000016, 0001655888-26-000056
```

v1 ships a **dated 2026-06-30 snapshot** of Ares Capital (`ARCC`), Blackstone Secured Lending (`BXSL`), and Blue Owl Capital Corp (`OBDC`). No SEC identity required to install or query. Refresh from live EDGAR is optional.

This is **not** a trading bot, not an IC memo writer, and not a 60-tool Bloomberg MCP.

## Why this exists

Agents invent private-credit quality. They will tell you a BDC book is clean, that a loan is unique to one lender, or that non-accrual is a Fitch default rate.

Public BDCs already disclose the look-through: every portfolio company, fair value, often PIK, and (in footnotes) non-accrual. The gap is a **cited overlap graph** plus a **balance-sheet reconcile that is allowed to fail**.

| Tool | Question it is allowed to answer |
| --- | --- |
| `loan_overlap` | Which of ARCC / BXSL / OBDC name this borrower? |
| `get_soi` | What does one BDC’s SOI say, with accession? |
| `nonaccrual_names` | Which names are tagged non-accrual, and by which method? |
| `reconcile_to_bs` | Does the SOI row-sum match `InvestmentOwnedAtFairValue`? |

On the bundled 2026 Q2 snapshot, `BXSL` reconciles within 3%. `ARCC` and `OBDC` do **not** — XBRL repeats rollup rows. The tool returns `reconcile_ok: false` instead of pretending the parser is NAV.

## Install (Cursor)

1. Install `uv` ([docs](https://docs.astral.sh/uv/getting-started/installation/)).
2. Paste `examples/cursor.mcp.json` into `~/.cursor/mcp.json`.

```json
{
  "mcpServers": {
    "bdc-lookthrough": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/Dxfory/edgar-mcp.git#subdirectory=bdc-lookthrough",
        "bdc-lookthrough-mcp"
      ]
    }
  }
}
```

Then ask:

> Which snapshot BDCs hold Auctane? Cite accession and fair value. Search Stamps.com too — it is an f/k/a.

Copy `skills/bdc-lookthrough/SKILL.md` into `.cursor/skills/bdc-lookthrough/SKILL.md` if you want the agent forbidden from web-searching BDC credit quality.

Claude Desktop: `examples/claude.mcp.json`.

## Python / CLI

```bash
uvx --from git+https://github.com/Dxfory/edgar-mcp.git#subdirectory=bdc-lookthrough \
  bdc-lookthrough overlap Anaplan
```

```python
from bdc_lookthrough import load_snapshot

snap = load_snapshot()
print(snap.overlap("Auctane")["tickers"])
print(snap.reconcile("BXSL")["reconcile_ok"])
print(snap.nonaccrual_names("ARCC")["count"])
```

From a clone:

```bash
cd bdc-lookthrough
python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/bdc-lookthrough overlap "PetVet"
.venv/bin/bdc-lookthrough reconcile ARCC
```

## Data contract

Every position carries:

- `accession_number`, `index_url`, `period`, `form`
- `company_name` as filed, plus `borrower_norm` and `aliases` (d/b/a, f/k/a)
- `fair_value`, `cost`, `pik_rate`, `investment_type`
- `extraction_method`

Reconcile payload:

- `soi_sum_fair_value` — sum of parsed SOI rows
- `bs_fair_value` — undimensioned `us-gaap:InvestmentOwnedAtFairValue`
- `reconcile_error_pct`, `reconcile_ok` (threshold 3%)

`data_mode` is `bundled_snapshot` until you point `BDC_LOOKTHROUGH_SNAPSHOT` at a refresh.

## Footguns

- **Name ≠ CUSIP.** `Guidehouse, Inc.` and `Guidehouse Inc.` match. `Romulus Intermediate Holdings 1 Inc. (dba PetVet Care Centers)` matches a PetVet query. Unrelated companies that share a short token can collide.
- **Non-accrual ≠ default.** PIK and amend-and-extend can still be accrual. `extraction_method=none` is a parse gap.
- **SOI sum ≠ NAV.** If `reconcile_ok` is false, do not treat the row-sum as the investment line.
- **v1 universe is three tickers.** Absence from ARCC/BXSL/OBDC is not absence from private credit.
- **Snapshot is dated.** The bundled file is the 10-Qs for the period ended 2026-06-30. It will go stale.

## Live refresh (optional)

Needs `EDGAR_IDENTITY` (SEC fair-access User-Agent) and extra deps:

```bash
export EDGAR_IDENTITY="Your Name you@example.com"
python -m pip install -e ".[live]"
bdc-lookthrough refresh --out snapshot.json.gz
export BDC_LOOKTHROUGH_SNAPSHOT=$PWD/snapshot.json.gz
```

Filing data is from the SEC EDGAR system. This project is not affiliated with the SEC, Ares, Blackstone, or Blue Owl.

## License

MIT.
