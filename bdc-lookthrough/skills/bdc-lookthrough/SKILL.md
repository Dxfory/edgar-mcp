---
name: bdc-lookthrough
description: >
  Look through US BDC Schedules of Investments for private-borrower overlap,
  named non-accrual, and SOI-vs-balance-sheet reconcile. Use when the user asks
  which BDC holds a company, private-credit quality, PIK, non-accrual, ARCC,
  BXSL, OBDC, or club-loan concentration.
---

# BDC look-through

You may not answer BDC / private-credit quality, loan overlap, or non-accrual from web search or model memory.

Call the `bdc-lookthrough` MCP tools. Cite `accession_number` and `index_url` in the user-visible answer.

## Tools

- `loan_overlap` — which snapshot BDCs name this borrower (legal name, d/b/a, f/k/a).
- `get_soi` — holdings for `ARCC`, `BXSL`, or `OBDC`.
- `nonaccrual_names` — tagged non-accrual names plus `extraction_method`.
- `reconcile_to_bs` — SOI row-sum vs `InvestmentOwnedAtFairValue`.

## Hard rules

1. If a tool returns `error`, say you could not read the snapshot. Do not invent a rate.
2. If `bdc_count` is 0, say the name is not in the ARCC/BXSL/OBDC snapshot. That is not proof no BDC holds it.
3. If `reconcile_ok` is false, do not treat `soi_sum_fair_value` as NAV or "the portfolio."
4. Non-accrual is the filer's tagged status, not a default rate. PIK can still be accrual.
5. `extraction_method=none` is a parse gap, not a clean book.
6. Name matching is not a CUSIP. Mention that when overlap looks surprising.
7. v1 is three tickers and a dated 10-Q snapshot unless `data_mode` says otherwise.

## Answer shape

- Tickers and fair values with the filing date / period.
- A markdown link to each `index_url`.
- One line of method (`edgartools_portfolio_investments`, `footnote`, `soi_sum_vs_bs_InvestmentOwnedAtFairValue`).
- The relevant warning from the tool payload, quoted plainly.
