import edgar_mcp.filings as filings
import pytest

from edgar_mcp.filings import (
    EdgarConfigError,
    classify_form4_code,
    ensure_identity,
    normalize_form,
    prefer_original_form,
)


@pytest.fixture(autouse=True)
def reset_identity_flag():
    filings._IDENTITY_DONE = False
    yield
    filings._IDENTITY_DONE = False


def test_identity_required(monkeypatch):
    monkeypatch.delenv("EDGAR_IDENTITY", raising=False)
    with pytest.raises(EdgarConfigError, match="EDGAR_IDENTITY"):
        ensure_identity()


def test_identity_requires_email(monkeypatch):
    monkeypatch.setenv("EDGAR_IDENTITY", "NoEmailHere")
    with pytest.raises(EdgarConfigError, match="contact email"):
        ensure_identity()


def test_form_must_be_10k_or_10q():
    with pytest.raises(ValueError, match="10-K or 10-Q"):
        normalize_form("20-F")


def test_form4_f_is_not_open_market():
    assert classify_form4_code("F")["open_market"] is False


def test_prefer_original_10k_skips_amendment():
    rows = [{"form": "10-K/A"}, {"form": "10-K"}]
    assert prefer_original_form(rows, "10-K")["form"] == "10-K"


def test_prefer_original_falls_back_to_amendment():
    rows = [{"form": "10-K/A"}]
    assert prefer_original_form(rows, "10-K")["form"] == "10-K/A"
