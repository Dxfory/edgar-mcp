"""Run tests that do not need edgartools, mcp, or the network."""

from __future__ import annotations

import io
import json
import logging
import os
import re
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


class PackageSurfaceTests(unittest.TestCase):
    def _read(self, *parts: str) -> str:
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
            return fh.read()

    def test_versions_match(self):
        pyproject = self._read("pyproject.toml")
        init_text = self._read("edgar_mcp", "__init__.py")
        with open(os.path.join(ROOT, "server.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
        py_ver = re.search(r'^version = "([^"]+)"', pyproject, re.M)
        init_ver = re.search(r'__version__ = "([^"]+)"', init_text)
        self.assertIsNotNone(py_ver)
        self.assertIsNotNone(init_ver)
        version = py_ver.group(1)
        self.assertEqual(init_ver.group(1), version)
        self.assertEqual(manifest["version"], version)
        self.assertEqual(manifest["packages"][0]["version"], version)
        self.assertEqual(manifest["packages"][0]["identifier"], "edgar-filings-mcp")
        self.assertIn("BDC", manifest["description"])
        self.assertLessEqual(len(manifest["description"]), 100)

    def test_mcp_pin_avoids_v2(self):
        self.assertIn('"mcp>=1.9,<2"', self._read("pyproject.toml"))

    def test_four_tools_only(self):
        server = self._read("edgar_mcp", "server.py")
        tools = re.findall(r"^def (get_[a-z0-9_]+)\(", server, re.M)
        self.assertEqual(
            tools,
            [
                "get_trading_symbols",
                "get_segment_revenue",
                "get_bdc_nonaccrual",
                "get_form4",
            ],
        )
        self.assertEqual(server.count("@mcp.tool()"), 4)

    def test_examples_stay_placeholders(self):
        paths = [
            ("README.md",),
            ("examples", "cursor.mcp.json"),
            ("examples", "claude.mcp.json"),
            (".env.example",),
        ]
        for parts in paths:
            text = self._read(*parts)
            self.assertNotIn("dxfory@", text, "/".join(parts))
            self.assertIn("you@example.com", text)

    def test_readme_installs_from_pypi(self):
        text = self._read("README.md")
        self.assertIn('"edgar-filings-mcp"', text)
        self.assertNotIn("not published yet", text.lower())
        self.assertIn("mcp>=1.9,<2", text)
        self.assertIn("mcp-name: io.github.Dxfory/edgar-mcp", text)
        cursor = self._read("examples", "cursor.mcp.json")
        self.assertIn('"edgar-filings-mcp"', cursor)
        self.assertNotIn("git+", cursor)

    def test_identity_redaction(self):
        self.addCleanup(os.environ.pop, "EDGAR_IDENTITY", None)
        os.environ["EDGAR_IDENTITY"] = "Ada Lovelace ada@example.com"
        record = logging.LogRecord(
            name="edgar",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Identity of the Edgar REST client set to [%s]",
            args=("Ada Lovelace ada@example.com",),
            exc_info=None,
        )
        self.assertTrue(filings._RedactIdentityFilter().filter(record))
        self.assertNotIn("ada@example.com", record.getMessage())
        self.assertIn("<redacted>", record.getMessage())

    def test_identity_redaction_on_child_logger_handler(self):
        self.addCleanup(os.environ.pop, "EDGAR_IDENTITY", None)
        os.environ["EDGAR_IDENTITY"] = "Ada Lovelace ada@example.com"
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.addFilter(filings._RedactIdentityFilter())
        log = logging.getLogger("edgar.settings.test")
        log.handlers = [handler]
        log.propagate = False
        log.setLevel(logging.INFO)
        log.info("Identity of the Edgar REST client set to [%s]", os.environ["EDGAR_IDENTITY"])
        text = stream.getvalue()
        self.assertNotIn("ada@example.com", text)
        self.assertIn("<redacted>", text)


if __name__ == "__main__":
    unittest.main()
