"""Run tests that do not need edgartools, mcp, or the network."""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from edgar_mcp.jsonutil import get_field, jsonable  # noqa: E402
import edgar_mcp.filings as filings  # noqa: E402
from edgar_mcp.filings import (  # noqa: E402
    EdgarConfigError,
    classify_form4_code,
    collect_segment_rows,
    collect_trading_symbols,
    ensure_identity,
    normalize_form,
    prefer_original_form,
    serialize_nonaccrual,
)


class JsonUtilTests(unittest.TestCase):
    def test_jsonable_round_trip_types(self):
        self.assertIsNone(jsonable(None))
        self.assertEqual(jsonable(3), 3)
        self.assertEqual(jsonable({"a": 1}), {"a": 1})
        self.assertEqual(jsonable((1, 2)), [1, 2])

    def test_get_field_dict_and_object(self):
        class Obj:
            ticker = "JPM"

        self.assertEqual(get_field({"ticker": "JPM"}, "ticker"), "JPM")
        self.assertEqual(get_field(Obj(), "ticker"), "JPM")
        self.assertEqual(get_field({}, "missing", default="x"), "x")


class IdentityTests(unittest.TestCase):
    def setUp(self):
        filings._IDENTITY_DONE = False

    def tearDown(self):
        filings._IDENTITY_DONE = False

    def test_identity_required(self):
        os.environ.pop("EDGAR_IDENTITY", None)
        with self.assertRaises(EdgarConfigError):
            ensure_identity()

    def test_identity_requires_email(self):
        os.environ["EDGAR_IDENTITY"] = "NoEmailHere"
        with self.assertRaises(EdgarConfigError):
            ensure_identity()
        os.environ.pop("EDGAR_IDENTITY", None)


class FormTests(unittest.TestCase):
    def test_default_10k(self):
        self.assertEqual(normalize_form(None), "10-K")
        self.assertEqual(normalize_form("10-q"), "10-Q")

    def test_rejects_other_forms(self):
        with self.assertRaises(ValueError) as ctx:
            normalize_form("8-K")
        self.assertIn("10-K or 10-Q", str(ctx.exception))


class TradingSymbolFootgunTests(unittest.TestCase):
    def test_lists_every_symbol_when_entity_info_is_last_wins(self):
        facts = [
            {
                "value": "GOOG",
                "concept": "dei:TradingSymbol",
                "context_ref": "c-1",
                "dimensions": None,
                "period_end": "2025-12-31",
            },
            {
                "value": "GOOGL",
                "concept": "dei:TradingSymbol",
                "context_ref": "c-2",
                "dimensions": {"StatementClassOfStockAxis": "ClassA"},
                "period_end": "2025-12-31",
            },
        ]
        out = collect_trading_symbols(facts, {"ticker": "GOOGL"})
        self.assertEqual(out["entity_info_ticker"], "GOOGL")
        self.assertEqual({row["symbol"] for row in out["trading_symbols"]}, {"GOOG", "GOOGL"})


class SegmentFootgunTests(unittest.TestCase):
    def test_keeps_dimensioned_product_revenue(self):
        facts = [
            {
                "value": "193737000000",
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "label": "Data Center",
                "dimensions": {"ProductOrServiceAxis": "DataCenterMember"},
                "period_start": "2025-01-27",
                "period_end": "2026-01-25",
                "units": "USD",
            }
        ]
        rows = collect_segment_rows("ProductOrServiceAxis", facts)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value"], 193737000000.0)
        self.assertEqual(rows[0]["axis"], "ProductOrServiceAxis")
        self.assertIn("DataCenterMember", str(rows[0]["dimensions"]))

    def test_drops_non_numeric_narrative(self):
        rows = collect_segment_rows("ProductOrServiceAxis", [{"value": "see note 18", "dimensions": {}}])
        self.assertEqual(rows, [])


class Form4FootgunTests(unittest.TestCase):
    def test_f_is_not_open_market(self):
        out = classify_form4_code("F")
        self.assertEqual(out["code"], "F")
        self.assertFalse(out["open_market"])
        self.assertIn("tax", out["code_meaning"])

    def test_p_is_open_market_buy(self):
        out = classify_form4_code("p")
        self.assertTrue(out["open_market"])
        self.assertIn("buy", out["code_meaning"])


class BdcNonaccrualFootgunTests(unittest.TestCase):
    def test_serialize_does_not_treat_none_method_as_clean_zero(self):
        result = type(
            "R",
            (),
            {
                "investments": [],
                "nonaccrual_rate": None,
                "extraction_method": "none",
                "nonaccrual_fair_value": None,
                "total_portfolio_fair_value": None,
                "num_nonaccrual": 0,
                "custom_concept_rate": None,
                "aggregate_concept_value": None,
                "warnings": ["no linked footnotes"],
            },
        )()
        out = serialize_nonaccrual(result, {"index_url": "https://www.sec.gov/example"})
        self.assertEqual(out["extraction_method"], "none")
        self.assertIsNone(out["nonaccrual_rate"])
        self.assertTrue(any("parse gap" in item or "none is not proof" in item for item in out["warnings"]))
        self.assertIn("no linked footnotes", out["warnings"])

    def test_prefer_original_form_skips_10k_amendment(self):
        picked = prefer_original_form([{"form": "10-K/A"}, {"form": "10-K"}], "10-K")
        self.assertEqual(picked["form"], "10-K")


if __name__ == "__main__":
    unittest.main()
