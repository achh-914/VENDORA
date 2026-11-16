"""Review store with an append-only, hash-chained audit log.

Cases are held as plain dicts (a CaseFile dumped to JSON). State lives in memory.
Give the store a database path (the VENDORA_DB environment variable) and every
case and audit event is also written to SQLite, so a restart loses nothing.
"""

import hashlib
import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

GENESIS = "0" * 64
DEFAULT_TENANT = "default"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    tenant TEXT NOT NULL DEFAULT 'default',
    case_id TEXT NOT NULL,
    case_json TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant, case_id)
);
CREATE TABLE IF NOT EXISTS events (
    tenant TEXT NOT NULL DEFAULT 'default',
    seq INTEGER NOT NULL,
    at TEXT NOT NULL,
    case_id TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    event TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    digest TEXT NOT NULL,
    PRIMARY KEY (tenant, seq)
);
"""

OLD_COLUMNS = {
    "cases": "case_id, case_json, status, source, created_at",
    "events": "seq, at, case_id, actor_type, actor, event, detail_json, prev_hash, digest",
}


class CaseStatus(StrEnum):
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class Decision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


STATUS_FOR = {
    Decision.APPROVED: CaseStatus.APPROVED,
    Decision.REJECTED: CaseStatus.REJECTED,
    Decision.CHANGES_REQUESTED: CaseStatus.CHANGES_REQUESTED,
}
CLOSED = {CaseStatus.APPROVED, CaseStatus.REJECTED}


class CaseExistsError(Exception):
    """A case with this id is already in the store."""


class CaseNotFoundError(Exception):
    """No case has this id."""


class CaseClosedError(Exception):
    """The case was already approved or rejected."""


@dataclass
class AuditEvent:
    seq: int
    at: str
    case_id: str
    actor_type: str
    actor: str
    event: str
    detail: dict[str, object]
    prev_hash: str
    digest: str


@dataclass
class CaseRecord:
    case: dict[str, object]
    status: CaseStatus
    source: str
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _digest(prev_hash: str, event: AuditEvent) -> str:
    body = {
        "prev": prev_hash,
        "seq": event.seq,
        "at": event.at,
        "case_id": event.case_id,
        "actor_type": event.actor_type,
        "actor": event.actor,
        "event": event.event,
        "detail": event.detail,
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class ReviewStore:
    def __init__(self, path: str | None = None) -> None:
        self._lock = threading.Lock()
        self._cases: dict[tuple[str, str], CaseRecord] = {}
        self._events: dict[str, list[AuditEvent]] = {}
        self._db: sqlite3.Connection | None = None
        if path:
            self._db = sqlite3.connect(path, check_same_thread=False)
            self._upgrade_old_tables()
            self._db.executescript(SCHEMA)
            self._copy_old_rows()
            self._load()

    def reset(self) -> None:
        with self._lock:
            self._cases.clear()
            self._events.clear()
            if self._db is not None:
                self._db.execute("DELETE FROM cases")
                self._db.execute("DELETE FROM events")
                self._db.commit()

    def add_case(
        self,
        case: dict[str, object],
        source: str = "api",
        tenant: str = DEFAULT_TENANT,
    ) -> CaseRecord:
        case_id = str(case["case_id"])
        with self._lock:
            if (tenant, case_id) in self._cases:
                raise CaseExistsError(case_id)
            record = CaseRecord(
                case=case,
                status=CaseStatus.AWAITING_APPROVAL,
                source=source,
                created_at=_now(),
            )
            self._cases[(tenant, case_id)] = record
            detail = {
                "finding": case["finding"],
                "delta": case["delta"],
                "source": source,
            }
            self._append(tenant, case_id, "system", "vendora", "case_created", detail)
            self._save_case(tenant, case_id, record)
            self._commit()
            return record

    def get(self, case_id: str, tenant: str = DEFAULT_TENANT) -> CaseRecord:
        with self._lock:
            record = self._cases.get((tenant, case_id))
        if record is None:
            raise CaseNotFoundError(case_id)
        return record

    def all_cases(self, tenant: str = DEFAULT_TENANT) -> list[CaseRecord]:
        with self._lock:
            return [r for (owner, _), r in self._cases.items() if owner == tenant]

    def decide(
        self,
        case_id: str,
        decision: Decision,
        decided_by: str,
        comment: str = "",
        tenant: str = DEFAULT_TENANT,
    ) -> CaseRecord:
        with self._lock:
            record = self._cases.get((tenant, case_id))
            if record is None:
                raise CaseNotFoundError(case_id)
            if record.status in CLOSED:
                raise CaseClosedError(case_id)
            record.status = STATUS_FOR[decision]
            self._append(
                tenant,
                case_id,
                "human",
                decided_by,
                "decision_" + decision.value,
                {"comment": comment},
            )
            if decision is Decision.APPROVED:
                for action in record.case.get("proposed_action", []):
                    detail = {"action": action, "simulated": True}
                    self._append(tenant, case_id, "system", "vendora", "action_simulated", detail)
            self._save_case(tenant, case_id, record)
            self._commit()
            return record

    def events_for(
        self, case_id: str, tenant: str = DEFAULT_TENANT
    ) -> tuple[list[AuditEvent], bool]:
        with self._lock:
            events = [e for e in self._events.get(tenant, []) if e.case_id == case_id]
            return events, self._chain_ok(tenant)

    def delete_tenant(self, tenant: str) -> int:
        """Erase every case and audit event of one customer. Returns the case count."""
        with self._lock:
            keys = [key for key in self._cases if key[0] == tenant]
            for key in keys:
                del self._cases[key]
            self._events.pop(tenant, None)
            if self._db is not None:
                self._db.execute("DELETE FROM cases WHERE tenant = ?", (tenant,))
                self._db.execute("DELETE FROM events WHERE tenant = ?", (tenant,))
                self._db.commit()
            return len(keys)

    def _append(
        self,
        tenant: str,
        case_id: str,
        actor_type: str,
        actor: str,
        event: str,
        detail: dict[str, object],
    ) -> AuditEvent:
        chain = self._events.setdefault(tenant, [])
        prev_hash = chain[-1].digest if chain else GENESIS
        item = AuditEvent(
            seq=len(chain) + 1,
            at=_now(),
            case_id=case_id,
            actor_type=actor_type,
            actor=actor,
            event=event,
            detail=detail,
            prev_hash=prev_hash,
            digest="",
        )
        item.digest = _digest(prev_hash, item)
        chain.append(item)
        self._save_event(tenant, item)
        return item

    def _chain_ok(self, tenant: str) -> bool:
        prev_hash = GENESIS
        for item in self._events.get(tenant, []):
            expected = _digest(prev_hash, item)
            if item.prev_hash != prev_hash or item.digest != expected:
                return False
            prev_hash = item.digest
        return True

    def _upgrade_old_tables(self) -> None:
        """A database made before tenants existed: set its tables aside to be copied over."""
        if self._db is None:
            return
        for table in OLD_COLUMNS:
            columns = [row[1] for row in self._db.execute(f"PRAGMA table_info({table})")]
            if columns and "tenant" not in columns:
                self._db.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
        self._db.commit()

    def _copy_old_rows(self) -> None:
        """Move the old rows into the new tables under the default tenant."""
        if self._db is None:
            return
        for table, columns in OLD_COLUMNS.items():
            exists = self._db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (f"{table}_old",),
            ).fetchone()
            if exists:
                self._db.execute(
                    f"INSERT INTO {table} (tenant, {columns}) "
                    f"SELECT '{DEFAULT_TENANT}', {columns} FROM {table}_old"
                )
                self._db.execute(f"DROP TABLE {table}_old")
        self._db.commit()

    def _load(self) -> None:
        if self._db is None:
            return
        cases = self._db.execute(
            "SELECT tenant, case_id, case_json, status, source, created_at "
            "FROM cases ORDER BY rowid"
        ).fetchall()
        for tenant, case_id, case_json, status, source, created_at in cases:
            self._cases[(tenant, case_id)] = CaseRecord(
                case=json.loads(case_json),
                status=CaseStatus(status),
                source=source,
                created_at=created_at,
            )
        events = self._db.execute(
            "SELECT tenant, seq, at, case_id, actor_type, actor, event, detail_json, "
            "prev_hash, digest FROM events ORDER BY tenant, seq"
        ).fetchall()
        for row in events:
            tenant, seq, at, case_id, actor_type, actor, event, detail_json, prev_hash, digest = row
            self._events.setdefault(tenant, []).append(
                AuditEvent(
                    seq=seq,
                    at=at,
                    case_id=case_id,
                    actor_type=actor_type,
                    actor=actor,
                    event=event,
                    detail=json.loads(detail_json),
                    prev_hash=prev_hash,
                    digest=digest,
                )
            )

    def _save_case(self, tenant: str, case_id: str, record: CaseRecord) -> None:
        if self._db is None:
            return
        self._db.execute(
            "INSERT OR REPLACE INTO cases "
            "(tenant, case_id, case_json, status, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                tenant,
                case_id,
                json.dumps(record.case),
                record.status.value,
                record.source,
                record.created_at,
            ),
        )

    def _save_event(self, tenant: str, item: AuditEvent) -> None:
        if self._db is None:
            return
        self._db.execute(
            "INSERT INTO events (tenant, seq, at, case_id, actor_type, actor, event, "
            "detail_json, prev_hash, digest) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tenant,
                item.seq,
                item.at,
                item.case_id,
                item.actor_type,
                item.actor,
                item.event,
                json.dumps(item.detail),
                item.prev_hash,
                item.digest,
            ),
        )

    def _commit(self) -> None:
        if self._db is not None:
            self._db.commit()


STORE = ReviewStore(os.getenv("VENDORA_DB") or None)
