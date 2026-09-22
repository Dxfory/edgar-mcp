# BDC Lookthrough

A small helper for reading **public BDC Schedules of Investments**: which of a few large BDCs disclose the same private borrower, with a filing URL you can open.

It is meant for Cursor / Claude and for Python notebooks. Please treat every number as a citation, not as investment advice.

```text
$ bdc-lookthrough overlap Auctane
tickers: ARCC, BXSL, OBDC
fair value: ~$543m across 3 positions
index: 0001628280-26-050307, 0001736035-26-000016, 0001655888-26-000056
```

v1 ships a **dated 2026-06-30 snapshot** of Ares Capital (`ARCC`), Blackstone Secured Lending (`BXSL`), and Blue Owl Capital Corp (`OBDC`). You can query it without an SEC identity. Refreshing from live EDGAR is optional and should follow the SEC’s fair-access User-Agent rules.

This package only answers look-through questions from those filings. It does not trade, write memos, or replace a full market-data terminal.

## Why this exists

Language models often guess private-credit quality — a clean book, a unique lender, or a default rate. Public BDCs already disclose a look-through: portfolio companies, fair value, sometimes PIK, and (in footnotes) non-accrual. This project turns that disclosure into four careful tools, and it lets reconcile **fail** when the XBRL rows do not match the balance sheet.

| Tool | Question it is allowed to answer |
| --- | --- |
| `loan_overlap` | Which of ARCC / BXSL / OBDC name this borrower? |
| `get_soi` | What does one BDC’s SOI say, with accession? |
| `nonaccrual_names` | Which names are tagged non-accrual, and by which method? |
| `reconcile_to_bs` | Does the SOI row-sum match `InvestmentOwnedAtFairValue`? |

On the bundled 2026 Q2 snapshot, `BXSL` is within 3%. `ARCC` and `OBDC` are not — the SOI extract still contains rollup rows. The tool returns `reconcile_ok: false` rather than presenting the row-sum as NAV. That is intentional.

## Install (Cursor)

1. Install `uv` ([docs](https://docs.astral.sh/uv/getting-started/installation/)).
2. Paste `examples/cursor.mcp.json` into `~/.cursor/mcp.json` (please keep a real email out of git; the default server does not need `EDGAR_IDENTITY`).

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

You can then ask:

> Which snapshot BDCs hold Auctane? Please cite accession and fair value. Stamps.com is an f/k/a — does that match?

Optional: copy `skills/bdc-lookthrough/SKILL.md` into `.cursor/skills/bdc-lookthrough/SKILL.md` so the agent prefers these tools over a web search for BDC credit quality.

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

Offline checks (no SEC traffic):

```bash
python tests/run_offline.py
python scripts/pressure.py
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

## Limitations (please read)

- **Name matching is not a CUSIP.** `Guidehouse, Inc.` and `Guidehouse Inc.` match. A d/b/a such as PetVet can match too. Bare words like `group` or `software` are ignored so they do not sweep the whole book. Collisions can still happen on distinctive short names.
- **Non-accrual is not a default rate.** PIK and amend-and-extend can still be accrual. `extraction_method=none` means the extractor did not find a signal.
- **SOI sum is not NAV.** If `reconcile_ok` is false, please do not treat the row-sum as the investment line.
- **v1 covers three tickers.** Absence from ARCC / BXSL / OBDC is not absence from private credit.
- **The snapshot is dated.** The bundled file is the 10-Qs for the period ended 2026-06-30.

## Live refresh (optional)

Please set `EDGAR_IDENTITY` to a name and a real email ([SEC FAQ](https://www.sec.gov/os/webmaster-faq#code-support)), then:

```bash
export EDGAR_IDENTITY="Your Name you@example.com"
python -m pip install -e ".[live]"
bdc-lookthrough refresh --out snapshot.json.gz
export BDC_LOOKTHROUGH_SNAPSHOT=$PWD/snapshot.json.gz
```

Filing data is from the SEC EDGAR system. This project is not affiliated with the SEC, Ares, Blackstone, or Blue Owl. Parsing uses [edgartools](https://github.com/dgunning/edgartools); errors in the extract are ours to report, not theirs.

## License

MIT.
