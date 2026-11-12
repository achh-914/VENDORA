"""In-memory review store with an append-only, hash-chained audit log.

Cases are held as plain dicts (a CaseFile dumped to JSON), so this module needs
no third-party packages. State lives in memory and is lost on restart.
"""

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

GENESIS = "0" * 64


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
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cases: dict[str, CaseRecord] = {}
        self._events: list[AuditEvent] = []

    def reset(self) -> None:
        with self._lock:
            self._cases.clear()
            self._events.clear()

    def add_case(self, case: dict[str, object], source: str = "api") -> CaseRecord:
        case_id = str(case["case_id"])
        with self._lock:
            if case_id in self._cases:
                raise CaseExistsError(case_id)
            record = CaseRecord(
                case=case,
                status=CaseStatus.AWAITING_APPROVAL,
                source=source,
                created_at=_now(),
            )
            self._cases[case_id] = record
            detail = {
                "finding": case["finding"],
                "delta": case["delta"],
                "source": source,
            }
            self._append(case_id, "system", "vendora", "case_created", detail)
            return record

    def get(self, case_id: str) -> CaseRecord:
        with self._lock:
            record = self._cases.get(case_id)
        if record is None:
            raise CaseNotFoundError(case_id)
        return record

    def all_cases(self) -> list[CaseRecord]:
        with self._lock:
            return list(self._cases.values())

    def decide(
        self,
        case_id: str,
        decision: Decision,
        decided_by: str,
        comment: str = "",
    ) -> CaseRecord:
        with self._lock:
            record = self._cases.get(case_id)
            if record is None:
                raise CaseNotFoundError(case_id)
            if record.status in CLOSED:
                raise CaseClosedError(case_id)
            record.status = STATUS_FOR[decision]
            self._append(
                case_id,
                "human",
                decided_by,
                "decision_" + decision.value,
                {"comment": comment},
            )
            if decision is Decision.APPROVED:
                for action in record.case.get("proposed_action", []):
                    detail = {"action": action, "simulated": True}
                    self._append(case_id, "system", "vendora", "action_simulated", detail)
            return record

    def events_for(self, case_id: str) -> tuple[list[AuditEvent], bool]:
        with self._lock:
            events = [e for e in self._events if e.case_id == case_id]
            return events, self._chain_ok()

    def _append(
        self,
        case_id: str,
        actor_type: str,
        actor: str,
        event: str,
        detail: dict[str, object],
    ) -> AuditEvent:
        prev_hash = self._events[-1].digest if self._events else GENESIS
        item = AuditEvent(
            seq=len(self._events) + 1,
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
        self._events.append(item)
        return item

    def _chain_ok(self) -> bool:
        prev_hash = GENESIS
        for item in self._events:
            expected = _digest(prev_hash, item)
            if item.prev_hash != prev_hash or item.digest != expected:
                return False
            prev_hash = item.digest
        return True


STORE = ReviewStore()
