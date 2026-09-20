"""Run tests that do not need edgartools, mcp, or the network."""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from edgar_mcp.jsonutil import get_field, jsonable  # noqa: E402
import edgar_mcp.filings as filings  # noqa: E402
from edgar_mcp.filings import EdgarConfigError, ensure_identity  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
