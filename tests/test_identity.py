import edgar_mcp.filings as filings
import pytest

from edgar_mcp.filings import EdgarConfigError, ensure_identity


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
