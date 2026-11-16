import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import pipeline
from app.agents.extraction import ExtractedDocument
from app.server import app
from app.store import STORE

FIXTURES = Path(__file__).parent / "fixtures"
PDF = {"Content-Type": "application/pdf"}


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("VENDORA_API_KEYS", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    STORE.reset()
    return TestClient(app)


def test_upload_page_is_served(client: TestClient) -> None:
    response = client.get("/upload")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Analyze" in response.text


def test_extract_returns_the_document(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pipeline,
        "extract_document",
        lambda path: ExtractedDocument.model_validate(_load("invoice.json")),
    )

    response = client.post("/extract", content=b"%PDF-1.4 data", headers=PDF)

    assert response.status_code == 200
    assert response.json()["doc_id"] == "INV-2041"


def test_extract_refuses_a_file_that_is_not_a_pdf(client: TestClient) -> None:
    response = client.post("/extract", content=b"hello", headers=PDF)
    assert response.status_code == 415
    assert "PDF" in response.json()["detail"]


def test_extract_refuses_an_oversized_file(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "MAX_PDF_BYTES", 10)
    response = client.post("/extract", content=b"%PDF" + b"0" * 50, headers=PDF)
    assert response.status_code == 413


def test_analyze_queues_cases_for_review(client: TestClient) -> None:
    body = {
        "invoice": _load("invoice.json"),
        "po": _load("po.json"),
        "contract": _load("contract.json"),
    }

    result = client.post("/analyze", json=body).json()

    assert result["discrepancies"] == 1
    assert result["cases"][0]["finding"] == "UNAGREED-FEE"
    assert result["cases"][0]["state"] == "created"
    queue = client.get("/cases").json()
    assert [item["source"] for item in queue] == ["upload"]
    assert client.post("/analyze", json=body).json()["cases"][0]["state"] == "already_in_queue"


def test_upload_endpoints_need_a_key_when_keys_are_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VENDORA_API_KEYS", "key-acme:acme")
    assert client.post("/extract", content=b"%PDF-1.4", headers=PDF).status_code == 401
    assert client.post("/analyze", json={}).status_code == 401


def test_uploaded_cases_stay_with_their_customer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VENDORA_API_KEYS", "key-acme:acme,key-nordic:nordic")
    body = {
        "invoice": _load("invoice.json"),
        "po": _load("po.json"),
        "contract": _load("contract.json"),
    }
    acme = {"X-API-Key": "key-acme"}
    nordic = {"X-API-Key": "key-nordic"}

    assert client.post("/analyze", json=body, headers=acme).status_code == 200

    assert len(client.get("/cases", headers=acme).json()) == 1
    assert client.get("/cases", headers=nordic).json() == []
