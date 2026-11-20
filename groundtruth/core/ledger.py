"""Ledger engine: cryptographic hash chain, event append, and access logging.

Enforces:
- Cryptographic hash chain over canonical JSON (Architecture section 4.3)
- Gapless sequential ordering per case (seq starts at 1)
- Integrity verification
- Append-only access logging (SEC-5)
"""

import hashlib
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from groundtruth.core.enums import EventType
from groundtruth.core.utils import Clock, IdGenerator, SystemClock, UUIDGenerator, canonical_json

GENESIS_HASH = "0" * 64


class LedgerIntegrityError(Exception):
    """Raised when ledger tamper detection fails."""

    pass


@dataclass(frozen=True)
class Event:
    """Immutable ledger event."""

    event_id: str
    case_id: str
    seq: int
    event_type: str
    actor: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str
    ts: str


def compute_event_hash(prev_hash: str, event_data_without_hash: Mapping[str, Any]) -> str:
    """Compute sha256(prev_hash || canonical_json(event_without_hash))."""
    serialized = canonical_json(event_data_without_hash)
    payload_to_hash = prev_hash + serialized
    return hashlib.sha256(payload_to_hash.encode("utf-8")).hexdigest()


def append_event(
    conn: sqlite3.Connection,
    case_id: str,
    event_type: EventType | str,
    actor: str,
    payload: dict[str, Any],
    ts: str | datetime | None = None,
    id_gen: IdGenerator | None = None,
    clock: Clock | None = None,
) -> Event:
    """Append a new event to the case's immutable ledger."""
    generator = id_gen or UUIDGenerator()
    time_provider = clock or SystemClock()

    if ts is None:
        ts_str = time_provider.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    elif isinstance(ts, datetime):
        utc_ts = ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
        ts_str = utc_ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        ts_str = str(ts)

    type_str = str(event_type.value if isinstance(event_type, EventType) else event_type)

    # Query last seq and hash for this case
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT seq, hash FROM events
        WHERE case_id = ?
        ORDER BY seq DESC LIMIT 1
        """,
        (case_id,),
    )
    last_row = cursor.fetchone()

    if last_row is None:
        seq = 1
        prev_hash = GENESIS_HASH
    else:
        seq = int(last_row["seq"]) + 1
        prev_hash = str(last_row["hash"])

    event_id = generator.generate("evt")

    event_without_hash = {
        "actor": actor,
        "case_id": case_id,
        "event_id": event_id,
        "event_type": type_str,
        "payload": payload,
        "prev_hash": prev_hash,
        "seq": seq,
        "ts": ts_str,
    }

    event_hash = compute_event_hash(prev_hash, event_without_hash)
    canonical_payload = canonical_json(payload)

    cursor.execute(
        """
        INSERT INTO events (
            event_id, case_id, seq, event_type, actor, payload, prev_hash, hash, ts
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            case_id,
            seq,
            type_str,
            actor,
            canonical_payload,
            prev_hash,
            event_hash,
            ts_str,
        ),
    )

    return Event(
        event_id=event_id,
        case_id=case_id,
        seq=seq,
        event_type=type_str,
        actor=actor,
        payload=payload,
        prev_hash=prev_hash,
        hash=event_hash,
        ts=ts_str,
    )


def log_access(
    conn: sqlite3.Connection,
    caller: str | None,
    target_case_id: str | None,
    endpoint: str,
    reason: str,
    ts: str | datetime | None = None,
    id_gen: IdGenerator | None = None,
    clock: Clock | None = None,
) -> str:
    """Log an access attempt that cannot be placed in a case ledger (SEC-5)."""
    generator = id_gen or UUIDGenerator()
    time_provider = clock or SystemClock()

    if ts is None:
        ts_str = time_provider.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    elif isinstance(ts, datetime):
        utc_ts = ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
        ts_str = utc_ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        ts_str = str(ts)

    log_id = generator.generate("acc")
    caller_token_prefix = caller[:8] if caller else None

    conn.execute(
        """
        INSERT INTO access_log (log_id, ts, caller, target_case_id, endpoint, reason)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (log_id, ts_str, caller_token_prefix, target_case_id, endpoint, reason),
    )

    return log_id


def verify_case_ledger(conn: sqlite3.Connection, case_id: str) -> bool:
    """Verify cryptographic integrity of a case's event ledger.

    Returns True if valid; raises LedgerIntegrityError if tampered.
    """
    import json

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT event_id, case_id, seq, event_type, actor, payload, prev_hash, hash, ts
        FROM events
        WHERE case_id = ?
        ORDER BY seq ASC
        """,
        (case_id,),
    )
    rows = cursor.fetchall()

    if not rows:
        return True

    expected_prev_hash = GENESIS_HASH

    for expected_seq, row in enumerate(rows, start=1):
        actual_seq = int(row["seq"])
        if actual_seq != expected_seq:
            raise LedgerIntegrityError(
                f"Gap in sequence for case {case_id}: expected {expected_seq}, got {actual_seq}"
            )

        actual_prev_hash = str(row["prev_hash"])
        if actual_prev_hash != expected_prev_hash:
            raise LedgerIntegrityError(
                f"Broken hash link at seq {actual_seq}: expected prev {expected_prev_hash}, "
                f"got {actual_prev_hash}"
            )

        # Re-compute hash
        payload_dict = json.loads(str(row["payload"]))
        event_without_hash = {
            "actor": str(row["actor"]),
            "case_id": case_id,
            "event_id": str(row["event_id"]),
            "event_type": str(row["event_type"]),
            "payload": payload_dict,
            "prev_hash": actual_prev_hash,
            "seq": actual_seq,
            "ts": str(row["ts"]),
        }

        recomputed_hash = compute_event_hash(actual_prev_hash, event_without_hash)
        actual_hash = str(row["hash"])

        if recomputed_hash != actual_hash:
            raise LedgerIntegrityError(
                f"Tampering detected at seq {actual_seq}: expected hash {recomputed_hash}, "
                f"got {actual_hash}"
            )

        expected_prev_hash = actual_hash

    return True
