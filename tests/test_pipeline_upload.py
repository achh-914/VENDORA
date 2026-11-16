import json
from pathlib import Path

import pytest

from app import pipeline
from app.agents.extraction import ExtractedDocument
from app.pipeline import UploadError
from app.store import STORE

FIXTURES = Path(__file__).parent / "fixtures"


def _doc(name: str) -> ExtractedDocument:
    return ExtractedDocument.model_validate(json.loads((FIXTURES / name).read_text()))


@pytest.fixture(autouse=True)
def _clean() -> None:
    STORE.reset()


def test_pdf_checks() -> None:
    pipeline.validate_pdf(b"%PDF-1.4 content")
    with pytest.raises(UploadError) as empty:
        pipeline.validate_pdf(b"")
    assert empty.value.status == 400
    with pytest.raises(UploadError) as wrong:
        pipeline.validate_pdf(b"MZ not a pdf")
    assert wrong.value.status == 415
    with pytest.raises(UploadError) as big:
        pipeline.validate_pdf(b"%PDF" + b"0" * 100, limit=50)
    assert big.value.status == 413


def test_extraction_needs_a_model_key(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(UploadError) as error:
        pipeline.extract_pdf(b"%PDF-1.4 x")
    assert error.value.status == 503


def test_extract_reads_the_pdf_and_removes_the_temp_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    seen = {}

    def fake(path: Path) -> ExtractedDocument:
        seen["path"] = path
        seen["bytes"] = path.read_bytes()
        return _doc("invoice.json")

    monkeypatch.setattr(pipeline, "extract_document", fake)

    result = pipeline.extract_pdf(b"%PDF-1.4 hello")

    assert result.doc_id == "INV-2041"
    assert seen["bytes"] == b"%PDF-1.4 hello"
    assert not seen["path"].exists()


def test_unreadable_document_gives_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test")

    def broken(path: Path) -> ExtractedDocument:
        raise ValueError("no structured data")

    monkeypatch.setattr(pipeline, "extract_document", broken)

    with pytest.raises(UploadError) as error:
        pipeline.extract_pdf(b"%PDF-1.4 x")
    assert error.value.status == 422


def test_analyze_and_store_for_one_customer() -> None:
    cases = pipeline.analyze_documents(_doc("invoice.json"), _doc("po.json"), _doc("contract.json"))

    first = pipeline.store_cases(cases, "acme")
    again = pipeline.store_cases(cases, "acme")
    other = pipeline.store_cases(cases, "nordic")

    assert [c["finding"] for c in first] == ["UNAGREED-FEE"]
    assert first[0]["state"] == "created"
    assert again[0]["state"] == "already_in_queue"
    assert other[0]["state"] == "created"
    assert len(STORE.all_cases("acme")) == 1
    assert len(STORE.all_cases("nordic")) == 1
    assert STORE.all_cases("default") == []


def test_clean_documents_make_no_cases() -> None:
    po = _doc("po.json")
    assert pipeline.analyze_documents(po, po, _doc("contract.json")) == []
