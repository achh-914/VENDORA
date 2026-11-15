"""Investigation agent: explains a finding using the contract and builds a case file.

Plain Python, no LLM. A clause must exist in the contract before it is cited.
"""

import re

from app.agents.extraction import ExtractedClause, ExtractedDocument
from app.agents.matching import Finding, _norm
from app.schemas import CaseFile, DiscrepancyType, Evidence, ProposedAction

# English and French (accents are removed before matching, so write terms without them).
FEE_TERMS = (
    "freight",
    "shipping",
    "handling",
    "surcharge",
    "delivery",
    "fee",
    "transport",
    "livraison",
    "frais",
    "franco",
    "majoration",
    "manutention",
    "supplement",
)
PROHIBITION_RE = re.compile(
    r"shall not invoice|may not invoice|not be invoiced|included in"
    r"|ne (?:peut|pourra|doit|devra)(?: pas)? factur"
    r"|ne factur\w* pas"
    r"|n'?(?:est|sont|sera|seront) pas factur"
    r"|(?:inclus|incluse|incluses|compris|comprise|comprises) dans"
    r"|\bfranco\b"
)
# A clause that allows the fee if agreed beforehand ("unless agreed in writing ...").
EXCEPTION_RE = re.compile(
    r"unless (?:agreed|approved|authori[sz]ed)|except (?:as|if|where|when) (?:agreed|approved)"
    r"|sauf (?:accord|convention|autorisation)|a moins (?:d'un accord|que)"
)


def _mentions_fee(text: str) -> bool:
    normalized = _norm(text)
    return any(re.search(rf"\b{term}", normalized) for term in FEE_TERMS)


def find_fee_clause(contract: ExtractedDocument) -> ExtractedClause | None:
    """Return the first clause that talks about fees and restricts invoicing them."""
    for clause in contract.clauses:
        if _mentions_fee(clause.text) and PROHIBITION_RE.search(_norm(clause.text)):
            return clause
    return None


def _exception_note(clause: ExtractedClause) -> str | None:
    """Warn when the clause lets the supplier charge the fee if it was agreed first."""
    if EXCEPTION_RE.search(_norm(clause.text)):
        return (
            f"Clause {clause.number} allows this fee if it was agreed in writing before the "
            "order. Check there is no such agreement before holding the invoice."
        )
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
    notes: list[str] = []

    if finding.type == DiscrepancyType.UNAGREED_FEE:
        clause = find_fee_clause(contract)
        if clause is not None:
            evidence.append(_clause_evidence(contract, clause))
            actions = [ProposedAction.HOLD_INVOICE, ProposedAction.DRAFT_SUPPLIER_MESSAGE]
            note = _exception_note(clause)
            if note:
                notes.append(note)
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
        notes=notes,
    )
