"""Tests that do not need live EDGAR. Library path only (mcp optional for surface checks)."""

from __future__ import annotations

import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from bdc_lookthrough.names import aliases_for, is_junk_borrower, normalize_borrower, query_matches
from bdc_lookthrough.snapshot import Snapshot, load_snapshot, reset_snapshot_cache


def _read(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


class NameTests(unittest.TestCase):
    def test_strips_inc_and_trailing_comma(self):
        self.assertEqual(normalize_borrower("Anaplan, Inc.,"), "anaplan")
        self.assertEqual(normalize_borrower("Guidehouse Inc."), "guidehouse")
        self.assertEqual(normalize_borrower("Guidehouse, Inc."), "guidehouse")

    def test_keeps_holdco_token(self):
        self.assertEqual(normalize_borrower("ML Holdco, Inc."), "ml holdco")

    def test_fka_alias(self):
        names = aliases_for("Auctane, Inc. (f/k/a Stamps.com Inc.)")
        self.assertIn("auctane", names)
        self.assertIn("stamps com", names)

    def test_dba_alias(self):
        names = aliases_for("Romulus Intermediate Holdings 1 Inc. (dba PetVet Care Centers)")
        self.assertTrue(any("petvet" in item for item in names))

    def test_junk_investment_types(self):
        self.assertTrue(is_junk_borrower(normalize_borrower("Subordinated")))
        self.assertTrue(is_junk_borrower(normalize_borrower("Equity")))
        self.assertFalse(is_junk_borrower(normalize_borrower("Auctane, Inc.")))

    def test_query_matches_token(self):
        self.assertTrue(query_matches("stamps", ["stamps com"]))
        self.assertTrue(query_matches("anaplan", ["anaplan"]))
        self.assertFalse(query_matches("ab", ["abc"]))


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reset_snapshot_cache()
        cls.snap = load_snapshot()

    def test_universe_is_three_bdcs(self):
        tickers = {item["ticker"] for item in self.snap.universe}
        self.assertEqual(tickers, {"ARCC", "BXSL", "OBDC"})

    def test_auctane_is_in_all_three(self):
        hit = self.snap.overlap("Auctane")
        self.assertEqual(hit["tickers"], ["ARCC", "BXSL", "OBDC"])
        self.assertEqual(hit["bdc_count"], 3)
        self.assertGreater(hit["total_fair_value"], 500_000_000)
        self.assertTrue(all(pos.get("accession_number") for pos in hit["positions"]))
        self.assertTrue(all(src.get("index_url", "").startswith("https://www.sec.gov/") for src in hit["sources"]))

    def test_stamps_fka_finds_auctane(self):
        hit = self.snap.overlap("Stamps.com")
        self.assertIn("OBDC", hit["tickers"])
        self.assertTrue(any("Auctane" in (pos.get("company_name") or "") for pos in hit["positions"]))

    def test_anaplan_three_bdcs(self):
        hit = self.snap.overlap("Anaplan")
        self.assertEqual(set(hit["tickers"]), {"ARCC", "BXSL", "OBDC"})

    def test_guidehouse_punctuation(self):
        hit = self.snap.overlap("Guidehouse")
        self.assertEqual(set(hit["tickers"]), {"BXSL", "OBDC"})

    def test_unknown_borrower_is_empty_not_error(self):
        hit = self.snap.overlap("DefinitelyNotAPortfolioCompanyXYZ")
        self.assertEqual(hit["bdc_count"], 0)
        self.assertEqual(hit["positions"], [])

    def test_bxsl_reconciles(self):
        out = self.snap.reconcile("BXSL")
        self.assertTrue(out["reconcile_ok"])
        self.assertIsNotNone(out["bs_fair_value"])
        self.assertLessEqual(abs(out["reconcile_error_pct"]), 0.03)

    def test_arcc_reports_gap(self):
        out = self.snap.reconcile("ARCC")
        self.assertFalse(out["reconcile_ok"])
        self.assertGreater(out["soi_sum_fair_value"], out["bs_fair_value"])
        self.assertTrue(any("rollups" in item.lower() or "NAV" in item for item in out["warnings"]))

    def test_nonaccrual_named_and_method(self):
        out = self.snap.nonaccrual_names("ARCC")
        self.assertGreater(out["count"], 0)
        block = out["blocks"][0]
        self.assertEqual(block["extraction_method"], "footnote")
        self.assertIsNotNone(block["nonaccrual_rate"])
        self.assertTrue(out["investments"][0]["company_name"])
        self.assertTrue(out["investments"][0]["accession_number"])

    def test_soi_cites_filing(self):
        out = self.snap.soi("OBDC", limit=5)
        self.assertEqual(out["source"]["ticker"], "OBDC")
        self.assertTrue(out["source"]["accession_number"])
        self.assertEqual(len(out["holdings"]), 5)
        self.assertGreater(out["n_holdings"], 5)

    def test_unknown_ticker_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self.snap.soi("NVDA")
        self.assertIn("Unknown BDC ticker", str(ctx.exception))


class SurfaceTests(unittest.TestCase):
    def test_four_mcp_tools(self):
        server = _read("src", "bdc_lookthrough", "server.py")
        tools = re.findall(r"@mcp\.tool\(\)\s*\ndef ([a-z0-9_]+)\(", server)
        self.assertEqual(tools, ["get_soi", "loan_overlap", "nonaccrual_names", "reconcile_to_bs"])
        self.assertEqual(server.count("@mcp.tool()"), 4)

    def test_examples_are_placeholders(self):
        for parts in (
            ("README.md",),
            ("examples", "cursor.mcp.json"),
            ("examples", "claude.mcp.json"),
            (".env.example",),
        ):
            text = _read(*parts)
            self.assertNotIn("dxfory@", text, "/".join(parts))
            if parts[0] != "README.md":
                self.assertNotIn("icloud.com", text)

    def test_readme_has_uvx_and_auctane(self):
        text = _read("README.md")
        self.assertIn("subdirectory=bdc-lookthrough", text)
        self.assertIn("Auctane", text)
        self.assertIn("reconcile_ok", text)
        self.assertIn("bdc-lookthrough-mcp", text)

    def test_mcp_pin(self):
        self.assertIn('"mcp>=1.9,<2"', _read("pyproject.toml"))

    def test_skill_forbids_web_search(self):
        text = _read("skills", "bdc-lookthrough", "SKILL.md")
        self.assertIn("web search", text.lower())
        self.assertIn("accession_number", text)

    def test_server_json_version(self):
        pyproject = _read("pyproject.toml")
        init_text = _read("src", "bdc_lookthrough", "__init__.py")
        manifest = json.loads(_read("server.json"))
        py_ver = re.search(r'^version = "([^"]+)"', pyproject, re.M)
        init_ver = re.search(r'__version__ = "([^"]+)"', init_text)
        self.assertEqual(py_ver.group(1), init_ver.group(1))
        self.assertEqual(manifest["version"], py_ver.group(1))
        self.assertLessEqual(len(manifest["description"]), 120)


if __name__ == "__main__":
    unittest.main()
