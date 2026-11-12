import pytest
from fastapi.testclient import TestClient

from app.server import app
from app.store import STORE

CASE = {
    "case_id": "CASE-API-1",
    "finding": "UNAGREED-FEE",
    "delta": 3000.0,
    "evidence": [{"doc": "invoice.pdf", "page": 1, "ref": "line 4"}],
    "proposed_action": ["HOLD_INVOICE", "DRAFT_SUPPLIER_MESSAGE"],
    "requires_human_approval": True,
}


@pytest.fixture
def client() -> TestClient:
    STORE.reset()
    return TestClient(app)


def test_review_page_is_served(client: TestClient) -> None:
    response = client.get("/review")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Vendora" in response.text


def test_create_and_list_case(client: TestClient) -> None:
    assert client.post("/cases", json=CASE).status_code == 201
    items = client.get("/cases").json()
    assert len(items) == 1
    assert items[0]["case_id"] == "CASE-API-1"
    assert items[0]["status"] == "awaiting_approval"
    assert items[0]["evidence_count"] == 1


def test_duplicate_case_returns_409(client: TestClient) -> None:
    client.post("/cases", json=CASE)
    assert client.post("/cases", json=CASE).status_code == 409


def test_case_without_evidence_is_rejected(client: TestClient) -> None:
    bad = {**CASE, "evidence": []}
    assert client.post("/cases", json=bad).status_code == 422


def test_approval_flow_and_audit_trail(client: TestClient) -> None:
    client.post("/cases", json=CASE)
    body = {"decision": "approved", "decided_by": "Meriem", "comment": "ok"}
    response = client.post("/cases/CASE-API-1/decision", json=body)
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    audit = client.get("/cases/CASE-API-1/audit").json()
    assert audit["chain_ok"] is True
    names = [event["event"] for event in audit["events"]]
    assert names[:2] == ["case_created", "decision_approved"]
    assert names.count("action_simulated") == 2


def test_blank_name_is_rejected(client: TestClient) -> None:
    client.post("/cases", json=CASE)
    body = {"decision": "approved", "decided_by": "   "}
    assert client.post("/cases/CASE-API-1/decision", json=body).status_code == 422


def test_closed_case_returns_409(client: TestClient) -> None:
    client.post("/cases", json=CASE)
    body = {"decision": "rejected", "decided_by": "Meriem"}
    client.post("/cases/CASE-API-1/decision", json=body)
    assert client.post("/cases/CASE-API-1/decision", json=body).status_code == 409


def test_unknown_case_returns_404(client: TestClient) -> None:
    body = {"decision": "approved", "decided_by": "Meriem"}
    assert client.get("/cases/NOPE").status_code == 404
    assert client.get("/cases/NOPE/audit").status_code == 404
    assert client.post("/cases/NOPE/decision", json=body).status_code == 404


def test_demo_case_is_created_once(client: TestClient) -> None:
    first = client.post("/demo/case")
    assert first.status_code == 201
    assert first.json()["source"] == "demo"
    assert client.post("/demo/case").status_code == 409
