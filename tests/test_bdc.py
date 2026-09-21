from decimal import Decimal
from types import SimpleNamespace

from edgar_mcp.filings import serialize_nonaccrual


def test_serialize_nonaccrual_keeps_rate_and_footnote():
    inv = SimpleNamespace(
        identifier="loan-1",
        company_name="Acme Software LLC",
        investment_type="First lien",
        fair_value=Decimal("25000000"),
        cost=Decimal("28000000"),
        footnote_text="Loan was on non-accrual status as of the reporting date.",
    )
    result = SimpleNamespace(
        investments=[inv],
        nonaccrual_rate=0.0123,
        extraction_method="footnote",
        nonaccrual_fair_value=Decimal("25000000"),
        total_portfolio_fair_value=Decimal("2032520325"),
        num_nonaccrual=1,
        custom_concept_rate=0.011,
        aggregate_concept_value=None,
        warnings=["computed rate differs from stated"],
    )
    out = serialize_nonaccrual(result, {"accession_number": "0001287750-26-000001"})
    assert out["extraction_method"] == "footnote"
    assert out["nonaccrual_rate"] == 0.0123
    assert out["nonaccrual_rate_pct"] == 1.23
    assert out["num_nonaccrual"] == 1
    assert out["investments"][0]["company_name"] == "Acme Software LLC"
    assert out["investments"][0]["fair_value"] == 25000000.0
    assert "non-accrual" in (out["investments"][0]["footnote_text"] or "")
    assert "computed rate differs from stated" in out["warnings"]
    assert any("not a Fitch" in item for item in out["warnings"])


def test_serialize_clips_long_footnote():
    inv = SimpleNamespace(
        identifier="x",
        company_name="Long",
        investment_type="Unitranche",
        fair_value=1,
        cost=1,
        footnote_text="x" * 500,
    )
    result = SimpleNamespace(
        investments=[inv],
        nonaccrual_rate=None,
        extraction_method="none",
        nonaccrual_fair_value=None,
        total_portfolio_fair_value=None,
        num_nonaccrual=1,
        custom_concept_rate=None,
        aggregate_concept_value=None,
        warnings=[],
    )
    text = serialize_nonaccrual(result, {})["investments"][0]["footnote_text"]
    assert text is not None
    assert len(text) == 400
    assert text.endswith("...")
