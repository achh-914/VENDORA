import sqlite3

import pytest

from app.store import CaseExistsError, Decision, ReviewStore

CASE = {
    "case_id": "INV-1-01",
    "finding": "UNAGREED-FEE",
    "delta": 3000.0,
    "evidence": [{"doc": "INV-1", "page": 1, "ref": "line 4"}],
    "proposed_action": ["HOLD_INVOICE"],
    "requires_human_approval": True,
}


def test_case_decision_and_audit_survive_a_restart(tmp_path):
    db = str(tmp_path / "vendora.db")
    first = ReviewStore(db)
    first.add_case(dict(CASE), source="api")
    first.decide("INV-1-01", Decision.APPROVED, "alice", "ok")

    second = ReviewStore(db)
    record = second.get("INV-1-01")
    events, chain_ok = second.events_for("INV-1-01")

    assert record.status.value == "approved"
    assert record.case["delta"] == 3000.0
    assert chain_ok is True
    assert [e.event for e in events] == [
        "case_created",
        "decision_approved",
        "action_simulated",
    ]
    assert events[1].actor == "alice"


def test_tampering_with_the_database_breaks_the_chain(tmp_path):
    db = str(tmp_path / "vendora.db")
    first = ReviewStore(db)
    first.add_case(dict(CASE), source="api")
    first.decide("INV-1-01", Decision.APPROVED, "alice")

    conn = sqlite3.connect(db)
    conn.execute("UPDATE events SET actor = 'mallory' WHERE seq = 2")
    conn.commit()
    conn.close()

    _, chain_ok = ReviewStore(db).events_for("INV-1-01")

    assert chain_ok is False


def test_a_saved_case_cannot_be_added_twice_after_restart(tmp_path):
    db = str(tmp_path / "vendora.db")
    ReviewStore(db).add_case(dict(CASE), source="api")

    with pytest.raises(CaseExistsError):
        ReviewStore(db).add_case(dict(CASE), source="api")


def test_without_a_path_the_store_stays_in_memory():
    store = ReviewStore()
    store.add_case(dict(CASE), source="api")

    assert store.get("INV-1-01").status.value == "awaiting_approval"
