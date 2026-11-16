import sqlite3

import pytest

from app.auth import load_keys, tenant_for
from app.store import CaseNotFoundError, Decision, ReviewStore

CASE = {
    "case_id": "CASE-1",
    "finding": "UNAGREED-FEE",
    "delta": 3000.0,
    "evidence": [{"doc": "invoice.pdf", "page": 1, "ref": "line 4"}],
    "proposed_action": ["HOLD_INVOICE", "DRAFT_SUPPLIER_MESSAGE"],
    "requires_human_approval": True,
}


def test_delete_tenant_erases_only_that_customer() -> None:
    store = ReviewStore()
    store.add_case(dict(CASE), tenant="acme")
    store.add_case(dict(CASE), tenant="nordic")

    assert store.delete_tenant("acme") == 1

    with pytest.raises(CaseNotFoundError):
        store.get("CASE-1", "acme")
    assert store.events_for("CASE-1", "acme") == ([], True)
    assert store.get("CASE-1", "nordic").case["case_id"] == "CASE-1"


def test_tenants_survive_a_restart(tmp_path) -> None:
    db = str(tmp_path / "v.db")
    first = ReviewStore(db)
    first.add_case(dict(CASE), tenant="acme")
    first.decide("CASE-1", Decision.REJECTED, "Meriem", tenant="acme")
    first.add_case(dict(CASE), tenant="nordic")

    second = ReviewStore(db)

    assert [r.status for r in second.all_cases("acme")] == ["rejected"]
    assert len(second.all_cases("nordic")) == 1
    assert second.events_for("CASE-1", "acme")[1] is True


def test_delete_tenant_is_permanent(tmp_path) -> None:
    db = str(tmp_path / "v.db")
    first = ReviewStore(db)
    first.add_case(dict(CASE), tenant="acme")
    first.delete_tenant("acme")

    assert ReviewStore(db).all_cases("acme") == []


def test_old_database_is_upgraded_to_the_default_tenant(tmp_path) -> None:
    db = str(tmp_path / "old.db")
    new = ReviewStore(db)
    new.add_case(dict(CASE))
    new.decide("CASE-1", Decision.APPROVED, "Meriem")
    expected = new.events_for("CASE-1")[0]
    # rebuild the file as the pre-tenant version wrote it
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        ALTER TABLE cases RENAME TO c2;
        ALTER TABLE events RENAME TO e2;
        CREATE TABLE cases (case_id TEXT PRIMARY KEY, case_json TEXT NOT NULL,
            status TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE events (seq INTEGER PRIMARY KEY, at TEXT NOT NULL,
            case_id TEXT NOT NULL, actor_type TEXT NOT NULL, actor TEXT NOT NULL,
            event TEXT NOT NULL, detail_json TEXT NOT NULL, prev_hash TEXT NOT NULL,
            digest TEXT NOT NULL);
        INSERT INTO cases SELECT case_id, case_json, status, source, created_at FROM c2;
        INSERT INTO events SELECT seq, at, case_id, actor_type, actor, event,
            detail_json, prev_hash, digest FROM e2;
        DROP TABLE c2;
        DROP TABLE e2;
        """
    )
    conn.commit()
    conn.close()

    upgraded = ReviewStore(db)

    events, chain_ok = upgraded.events_for("CASE-1")
    assert chain_ok is True
    assert [e.digest for e in events] == [e.digest for e in expected]
    assert upgraded.get("CASE-1").status == "approved"


def test_key_table_parsing() -> None:
    import os

    os.environ["VENDORA_API_KEYS"] = " k1:Acme , k2:nordic-gmbh "
    try:
        assert load_keys() == {"k1": "acme", "k2": "nordic-gmbh"}
        os.environ["VENDORA_API_KEYS"] = "k1:bad tenant!"
        with pytest.raises(ValueError, match="Bad VENDORA_API_KEYS"):
            load_keys()
    finally:
        del os.environ["VENDORA_API_KEYS"]
    assert tenant_for("k1", {"k1": "acme"}) == "acme"
    assert tenant_for("k2", {"k1": "acme"}) is None
    assert tenant_for(None, {"k1": "acme"}) is None
