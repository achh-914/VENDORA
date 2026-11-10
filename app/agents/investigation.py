"""Investigation agent: explains a finding using the contract and builds a case file.

Plain Python, no LLM. A clause must exist in the contract before it is cited.
"""

import re

from app.agents.extraction import ExtractedClause, ExtractedDocument
from app.agents.matching import Finding
from app.schemas import CaseFile, DiscrepancyType, Evidence, ProposedAction

FEE_TERMS = ("freight", "shipping", "handling", "surcharge", "delivery", "fee")
PROHIBITION_RE = re.compile(
    r"shall not invoice|may not invoice|not be invoiced|included in", re.IGNORECASE
)


def _mentions_fee(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(rf"\b{term}", lowered) for term in FEE_TERMS)


def find_fee_clause(contract: ExtractedDocument) -> ExtractedClause | None:
    """Return the first clause that talks about fees and restricts invoicing them."""
    for clause in contract.clauses:
        if _mentions_fee(clause.text) and PROHIBITION_RE.search(clause.text):
            return clause
    return None


def _clause_evidence(contract: ExtractedDocument, clause: ExtractedClause) -> Evidence:
    return Evidence(
        doc=contract.doc_id,
        page=clause.page,
        ref=f"clause {clause.number}: {clause.text}",
    )


def investigate(
    finding: Finding, contract: ExtractedDocument, case_id: str = "CASE-0001"
) -> CaseFile:
    """Build a case file. Actions are only proposed, never executed."""
    evidence = list(finding.evidence)
    actions: list[ProposedAction] = []

    if finding.type == DiscrepancyType.UNAGREED_FEE:
        clause = find_fee_clause(contract)
        if clause is not None:
            evidence.append(_clause_evidence(contract, clause))
            actions = [ProposedAction.HOLD_INVOICE, ProposedAction.DRAFT_SUPPLIER_MESSAGE]
        else:
            actions = [ProposedAction.ESCALATE]
    else:
        actions = [ProposedAction.ESCALATE]

    return CaseFile(
        case_id=case_id,
        finding=finding.type,
        delta=finding.delta,
        evidence=evidence,
        proposed_action=actions,
        requires_human_approval=True,
    )
