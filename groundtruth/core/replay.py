"""Replay engine for GroundTruth.

Enforces:
- INV-2: State is derived. Replaying events 1..N yields identical state.
- In-memory pure fold over reducer.apply without database mutation.
"""

import json
import sqlite3

from groundtruth.core.ledger import Event
from groundtruth.core.models import CaseState
from groundtruth.core.reducer import apply


def replay_case(conn: sqlite3.Connection, case_id: str, upto_seq: int | None = None) -> CaseState:
    """Reconstruct case state at any event sequence by replaying events through the pure reducer."""
    cursor = conn.cursor()

    if upto_seq is not None:
        cursor.execute(
            """
            SELECT event_id, case_id, seq, event_type, actor, payload, prev_hash, hash, ts
            FROM events
            WHERE case_id = ? AND seq <= ?
            ORDER BY seq ASC
            """,
            (case_id, upto_seq),
        )
    else:
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
    state = CaseState(case_id=case_id)

    for row in rows:
        payload_val = row["payload"]
        try:
            payload_dict = json.loads(payload_val) if isinstance(payload_val, str) else payload_val
        except Exception:
            payload_dict = {}

        event = Event(
            event_id=row["event_id"],
            case_id=row["case_id"],
            seq=int(row["seq"]),
            event_type=row["event_type"],
            actor=row["actor"],
            payload=payload_dict,
            prev_hash=row["prev_hash"],
            hash=row["hash"],
            ts=row["ts"],
        )

        state = apply(state, event)

    return state
