from fastapi.testclient import TestClient

from app.main import app
from app.schemas import CaseFile, DiscrepancyType, Evidence

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_case_file_requires_human_approval_by_default():
    case = CaseFile(
        case_id="CASE-0001",
        finding=DiscrepancyType.UNAGREED_FEE,
        delta=3000.0,
        evidence=[Evidence(doc="invoice.pdf", page=1, ref="line 4: Freight surcharge")],
    )
    assert case.requires_human_approval is True
