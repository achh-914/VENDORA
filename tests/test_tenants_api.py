import pytest
from fastapi.testclient import TestClient

from app.server import app
from app.store import STORE

CASE = {
    "case_id": "CASE-1",
    "finding": "UNAGREED-FEE",
    "delta": 3000.0,
    "evidence": [{"doc": "invoice.pdf", "page": 1, "ref": "line 4"}],
    "proposed_action": ["HOLD_INVOICE", "DRAFT_SUPPLIER_MESSAGE"],
    "requires_human_approval": True,
}
ACME = {"X-API-Key": "key-acme"}
NORDIC = {"X-API-Key": "key-nordic"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("VENDORA_API_KEYS", "key-acme:acme,key-nordic:nordic")
    STORE.reset()
    return TestClient(app)


def test_no_keys_configured_means_no_login_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VENDORA_API_KEYS", raising=False)
    STORE.reset()
    assert TestClient(app).get("/cases").status_code == 200


def test_missing_or_wrong_key_is_refused(client: TestClient) -> None:
    assert client.get("/cases").status_code == 401
    assert client.get("/cases", headers={"X-API-Key": "nope"}).status_code == 401
    assert client.post("/cases", json=CASE).status_code == 401


def test_customer_sees_only_own_cases(client: TestClient) -> None:
    assert client.post("/cases", json=CASE, headers=ACME).status_code == 201
    assert len(client.get("/cases", headers=ACME).json()) == 1
    assert client.get("/cases", headers=NORDIC).json() == []


def test_customer_cannot_read_or_decide_another_customers_case(client: TestClient) -> None:
    client.post("/cases", json=CASE, headers=ACME)
    assert client.get("/cases/CASE-1", headers=NORDIC).status_code == 404
    assert client.get("/cases/CASE-1/audit", headers=NORDIC).status_code == 404
    body = {"decision": "approved", "decided_by": "Eve"}
    assert client.post("/cases/CASE-1/decision", json=body, headers=NORDIC).status_code == 404
    assert client.get("/cases/CASE-1", headers=ACME).json()["status"] == "awaiting_approval"


def test_same_case_id_can_exist_for_two_customers(client: TestClient) -> None:
    assert client.post("/cases", json=CASE, headers=ACME).status_code == 201
    assert client.post("/cases", json=CASE, headers=NORDIC).status_code == 201
    assert client.post("/cases", json=CASE, headers=ACME).status_code == 409


def test_each_customer_has_own_audit_chain(client: TestClient) -> None:
    client.post("/cases", json=CASE, headers=ACME)
    client.post("/cases", json=CASE, headers=NORDIC)
    client.post(
        "/cases/CASE-1/decision",
        json={"decision": "rejected", "decided_by": "Meriem"},
        headers=ACME,
    )
    acme = client.get("/cases/CASE-1/audit", headers=ACME).json()
    nordic = client.get("/cases/CASE-1/audit", headers=NORDIC).json()
    assert acme["chain_ok"] is True
    assert nordic["chain_ok"] is True
    assert [e["seq"] for e in acme["events"]] == [1, 2]
    assert [e["seq"] for e in nordic["events"]] == [1]
    assert nordic["events"][0]["prev_hash"] == "0" * 64
