import pytest

from app.store import (
    STORE,
    CaseClosedError,
    CaseExistsError,
    CaseNotFoundError,
    CaseStatus,
    Decision,
)


def make_case(case_id: str = "CASE-1") -> dict:
    return {
        "case_id": case_id,
        "finding": "UNAGREED-FEE",
        "delta": 3000.0,
        "evidence": [{"doc": "invoice.pdf", "page": 1, "ref": "line 4"}],
        "proposed_action": ["HOLD_INVOICE", "DRAFT_SUPPLIER_MESSAGE"],
        "requires_human_approval": True,
    }


@pytest.fixture(autouse=True)
def _clean_store() -> None:
    STORE.reset()


def event_names(case_id: str) -> list[str]:
    events, _ = STORE.events_for(case_id)
    return [event.event for event in events]


def test_new_case_waits_for_approval_and_is_logged() -> None:
    record = STORE.add_case(make_case())
    assert record.status == CaseStatus.AWAITING_APPROVAL
    assert event_names("CASE-1") == ["case_created"]


def test_duplicate_case_is_rejected() -> None:
    STORE.add_case(make_case())
    with pytest.raises(CaseExistsError):
        STORE.add_case(make_case())


def test_approval_is_logged_and_actions_are_only_simulated() -> None:
    STORE.add_case(make_case())
    record = STORE.decide("CASE-1", Decision.APPROVED, "Meriem", "ok")
    assert record.status == CaseStatus.APPROVED
    assert event_names("CASE-1") == [
        "case_created",
        "decision_approved",
        "action_simulated",
        "action_simulated",
    ]
    events, _ = STORE.events_for("CASE-1")
    assert all(event.detail["simulated"] for event in events[2:])
    assert events[1].actor_type == "human"
    assert events[1].actor == "Meriem"


def test_rejection_does_not_simulate_any_action() -> None:
    STORE.add_case(make_case())
    STORE.decide("CASE-1", Decision.REJECTED, "Meriem")
    assert event_names("CASE-1") == ["case_created", "decision_rejected"]


def test_changes_requested_keeps_the_case_open() -> None:
    STORE.add_case(make_case())
    record = STORE.decide("CASE-1", Decision.CHANGES_REQUESTED, "Meriem", "check PO")
    assert record.status == CaseStatus.CHANGES_REQUESTED
    record = STORE.decide("CASE-1", Decision.APPROVED, "Meriem")
    assert record.status == CaseStatus.APPROVED


def test_closed_case_cannot_be_decided_again() -> None:
    STORE.add_case(make_case())
    STORE.decide("CASE-1", Decision.REJECTED, "Meriem")
    with pytest.raises(CaseClosedError):
        STORE.decide("CASE-1", Decision.APPROVED, "Meriem")


def test_unknown_case_raises() -> None:
    with pytest.raises(CaseNotFoundError):
        STORE.get("NOPE")
    with pytest.raises(CaseNotFoundError):
        STORE.decide("NOPE", Decision.APPROVED, "Meriem")


def test_audit_chain_is_global_and_filtered_per_case() -> None:
    STORE.add_case(make_case("A"))
    STORE.add_case(make_case("B"))
    STORE.decide("A", Decision.REJECTED, "Meriem")
    events_a, chain_ok = STORE.events_for("A")
    events_b, _ = STORE.events_for("B")
    assert chain_ok
    assert [event.case_id for event in events_a] == ["A", "A"]
    assert [event.case_id for event in events_b] == ["B"]


def test_audit_chain_detects_tampering() -> None:
    STORE.add_case(make_case())
    STORE.decide("CASE-1", Decision.REJECTED, "Meriem", "no")
    events, chain_ok = STORE.events_for("CASE-1")
    assert chain_ok
    events[1].detail["comment"] = "yes"
    _, chain_ok = STORE.events_for("CASE-1")
    assert not chain_ok
