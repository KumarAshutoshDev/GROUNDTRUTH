"""Projector: The ONLY writer of GroundTruth projection tables.

Enforces:
- INV-3: Single write path. SQL writes (INSERT/UPDATE/DELETE) on cases, facts,
  fact_edges, and negative_checks exist exclusively in this module, executed
  only by applying operations derived by core/reducer.py from a ledger event.
"""

import json
import sqlite3
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from groundtruth.core.enums import EventType
from groundtruth.core.ledger import Event, append_event, log_access
from groundtruth.core.models import (
    CaseModel,
    CaseState,
    EdgeModel,
    FactModel,
    NegativeCheckModel,
    Op,
    OpType,
)
from groundtruth.core.reducer import diff
from groundtruth.core.utils import Clock, IdGenerator, canonical_json

EventListener = Callable[[Event], None]
_event_listeners: list[EventListener] = []


def add_event_listener(listener: EventListener) -> None:
    """Register a callback for newly appended events."""
    if listener not in _event_listeners:
        _event_listeners.append(listener)


def remove_event_listener(listener: EventListener) -> None:
    """Unregister an event callback."""
    if listener in _event_listeners:
        _event_listeners.remove(listener)


def notify_event_listeners(event: Event) -> None:
    """Broadcast an event to all registered listeners."""
    for listener in list(_event_listeners):
        try:
            listener(event)
        except Exception:
            pass


def load_case_projection(conn: sqlite3.Connection, case_id: str) -> CaseState:
    """Read the current projection state for a case from SQLite."""
    cursor = conn.cursor()

    # Load case
    cursor.execute(
        """
        SELECT case_id, domain_pack, trigger, state, opened_at, concluded_at, conclusion_fact_id
        FROM cases WHERE case_id = ?
        """,
        (case_id,),
    )
    case_row = cursor.fetchone()
    case_model = None
    if case_row:
        trigger_val = case_row["trigger"]
        try:
            trigger_dict = json.loads(trigger_val) if isinstance(trigger_val, str) else trigger_val
        except Exception:
            trigger_dict = {}
        case_model = CaseModel(
            case_id=case_row["case_id"],
            domain_pack=case_row["domain_pack"],
            trigger=trigger_dict,
            state=case_row["state"],
            opened_at=case_row["opened_at"],
            concluded_at=case_row["concluded_at"],
            conclusion_fact_id=case_row["conclusion_fact_id"],
        )

    # Load facts
    cursor.execute(
        """
        SELECT fact_id, case_id, type, value, source, source_type, agent_id, created_at,
               self_confidence, own_trust, effective_trust, evidence_ref, status, verifier_state,
               entity_key, volatile, is_conclusion
        FROM facts WHERE case_id = ?
        """,
        (case_id,),
    )
    facts_dict: dict[str, FactModel] = {}
    for row in cursor.fetchall():
        val = row["value"]
        try:
            val_parsed = json.loads(val) if isinstance(val, str) else val
        except Exception:
            val_parsed = val

        fid = row["fact_id"]
        facts_dict[fid] = FactModel(
            fact_id=fid,
            case_id=row["case_id"],
            type=row["type"],
            value=val_parsed,
            source=row["source"],
            source_type=row["source_type"],
            agent_id=row["agent_id"],
            created_at=row["created_at"],
            self_confidence=float(row["self_confidence"]),
            own_trust=float(row["own_trust"]),
            effective_trust=float(row["effective_trust"]),
            evidence_ref=row["evidence_ref"],
            status=row["status"],
            verifier_state=row["verifier_state"],
            entity_key=row["entity_key"],
            volatile=int(row["volatile"]),
            is_conclusion=int(row["is_conclusion"]),
            derived_from=[],
        )

    # Load edges
    cursor.execute(
        """
        SELECT fe.child_id, fe.parent_id
        FROM fact_edges fe
        JOIN facts f ON fe.child_id = f.fact_id
        WHERE f.case_id = ?
        """,
        (case_id,),
    )
    edges_list: list[EdgeModel] = []
    for erow in cursor.fetchall():
        child = erow["child_id"]
        parent = erow["parent_id"]
        edges_list.append(EdgeModel(child_id=child, parent_id=parent))
        if child in facts_dict and parent not in facts_dict[child].derived_from:
            facts_dict[child].derived_from.append(parent)

    # Load negative checks
    cursor.execute(
        """
        SELECT check_id, case_id, fact_id, check_type, scope, window_start, window_end, expires_at
        FROM negative_checks WHERE case_id = ?
        """,
        (case_id,),
    )
    neg_dict: dict[str, NegativeCheckModel] = {}
    for nrow in cursor.fetchall():
        scope_val = nrow["scope"]
        try:
            scope_list = json.loads(scope_val) if isinstance(scope_val, str) else scope_val
        except Exception:
            scope_list = []

        cid = nrow["check_id"]
        neg_dict[cid] = NegativeCheckModel(
            check_id=cid,
            case_id=nrow["case_id"],
            fact_id=nrow["fact_id"],
            check_type=nrow["check_type"],
            scope=scope_list,
            window_start=nrow["window_start"],
            window_end=nrow["window_end"],
            expires_at=nrow["expires_at"],
        )

    return CaseState(
        case_id=case_id,
        case=case_model,
        facts=facts_dict,
        edges=edges_list,
        negative_checks=neg_dict,
    )


def execute_ops(conn: sqlite3.Connection, ops: Sequence[Op]) -> None:
    """Execute pure reducer operations as SQL against projection tables (INV-3)."""
    cursor = conn.cursor()

    for op in ops:
        d = op.data

        if op.op_type == OpType.INSERT_CASE:
            cursor.execute(
                """
                INSERT INTO cases (
                    case_id, domain_pack, trigger, state,
                    opened_at, concluded_at, conclusion_fact_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d["case_id"],
                    d["domain_pack"],
                    canonical_json(d["trigger"]),
                    d["state"],
                    d["opened_at"],
                    d["concluded_at"],
                    d["conclusion_fact_id"],
                ),
            )

        elif op.op_type == OpType.UPDATE_CASE:
            set_clauses = []
            params = []
            for k in ("state", "concluded_at", "conclusion_fact_id"):
                if k in d:
                    set_clauses.append(f"{k} = ?")
                    params.append(d[k])
            params.append(d["case_id"])
            query = f"UPDATE cases SET {', '.join(set_clauses)} WHERE case_id = ?"
            cursor.execute(query, params)

        elif op.op_type == OpType.INSERT_FACT:
            cursor.execute(
                """
                INSERT INTO facts (
                    fact_id, case_id, type, value, source, source_type, agent_id, created_at,
                    self_confidence, own_trust, effective_trust, evidence_ref, status,
                    verifier_state, entity_key, volatile, is_conclusion
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d["fact_id"],
                    d["case_id"],
                    d["type"],
                    canonical_json(d["value"]),
                    d["source"],
                    d["source_type"],
                    d["agent_id"],
                    d["created_at"],
                    d["self_confidence"],
                    d["own_trust"],
                    d["effective_trust"],
                    d["evidence_ref"],
                    d["status"],
                    d["verifier_state"],
                    d.get("entity_key"),
                    d.get("volatile", 0),
                    d.get("is_conclusion", 0),
                ),
            )

        elif op.op_type == OpType.UPDATE_FACT:
            set_clauses = []
            params = []
            for k in (
                "status",
                "verifier_state",
                "own_trust",
                "effective_trust",
                "source_type",
                "self_confidence",
            ):
                if k in d:
                    set_clauses.append(f"{k} = ?")
                    params.append(d[k])
            params.append(d["fact_id"])
            query = f"UPDATE facts SET {', '.join(set_clauses)} WHERE fact_id = ?"
            cursor.execute(query, params)

        elif op.op_type == OpType.INSERT_EDGE:
            cursor.execute(
                """
                INSERT OR IGNORE INTO fact_edges (child_id, parent_id)
                VALUES (?, ?)
                """,
                (d["child_id"], d["parent_id"]),
            )

        elif op.op_type == OpType.INSERT_NEGATIVE:
            cursor.execute(
                """
                INSERT OR REPLACE INTO negative_checks (
                    check_id, case_id, fact_id, check_type,
                    scope, window_start, window_end, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d["check_id"],
                    d["case_id"],
                    d["fact_id"],
                    d["check_type"],
                    canonical_json(d["scope"]),
                    d["window_start"],
                    d["window_end"],
                    d.get("expires_at"),
                ),
            )


def append_and_project(
    conn: sqlite3.Connection,
    case_id: str,
    event_type: EventType | str,
    actor: str,
    payload: dict[str, Any],
    ts: str | datetime | None = None,
    id_gen: IdGenerator | None = None,
    clock: Clock | None = None,
) -> Event:
    """Atomic ledger append and projection execution (INV-3).

    One transaction:
      1. Append event to ledger (events table)
      2. Load current case state from projection tables (read-only)
      3. Compute ops = reducer.diff(state, event)
      4. Execute ops as SQL
      5. Commit, or rollback on any error
    """
    with conn:
        # Enforce CASE-3: CLOSED case's ledger is frozen. No event is appended to it.
        cursor = conn.cursor()
        cursor.execute("SELECT state FROM cases WHERE case_id = ?", (case_id,))
        case_row = cursor.fetchone()
        if case_row and case_row["state"] == "CLOSED":
            log_access(
                conn=conn,
                caller=actor,
                target_case_id=case_id,
                endpoint="ledger_append",
                reason="closed_case_ledger_frozen",
            )
            raise PermissionError(f"Case '{case_id}' is CLOSED; ledger is frozen (CASE-3)")

        # 1. Append event to ledger
        event = append_event(
            conn=conn,
            case_id=case_id,
            event_type=event_type,
            actor=actor,
            payload=payload,
            ts=ts,
            id_gen=id_gen,
            clock=clock,
        )

        # 2. Load current projection state
        state = load_case_projection(conn, case_id)

        # 3. Derive operations using pure reducer
        ops = diff(state, event)

        # 4. Execute operations against projection tables
        execute_ops(conn, ops)

    notify_event_listeners(event)
    return event
