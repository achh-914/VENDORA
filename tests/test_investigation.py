from pathlib import Path

from app.agents.extraction import ExtractedDocument
from app.agents.investigation import investigate
from app.agents.matching import match_documents
from app.schemas import DiscrepancyType, ProposedAction

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return ExtractedDocument.model_validate_json((FIXTURES / name).read_text())


def test_unagreed_freight_is_traced_to_clause_4_2():
    findings = match_documents(_load("invoice.json"), _load("po.json"))
    case = investigate(findings[0], _load("contract.json"))

    assert case.finding == DiscrepancyType.UNAGREED_FEE
    assert case.delta == 3000.0
    assert case.requires_human_approval is True
    assert ProposedAction.HOLD_INVOICE in case.proposed_action

    docs = {item.doc for item in case.evidence}
    assert docs == {"INV-2041", "PO-4471", "MSA-ACME-2025"}

    clause_evidence = next(e for e in case.evidence if e.doc == "MSA-ACME-2025")
    assert clause_evidence.page == 6
    assert "4.2" in clause_evidence.ref


def test_without_matching_clause_the_case_is_escalated():
    findings = match_documents(_load("invoice.json"), _load("po.json"))
    contract = _load("contract.json")
    contract.clauses = []

    case = investigate(findings[0], contract)

    assert case.proposed_action == [ProposedAction.ESCALATE]
    assert case.requires_human_approval is True
