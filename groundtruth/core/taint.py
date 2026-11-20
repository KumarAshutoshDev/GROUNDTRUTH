"""Contamination & Taint Engine (INV-9, Architecture Section 7).

Recursively propagates TAINTED status downstream along fact_edges
when an ancestor fact is retracted or invalidated.
Taint is sticky (INV-9): tainted facts only return to ACTIVE via HUMAN_OVERRIDE
or replacement by a superseding fact.
"""

from __future__ import annotations

import sqlite3
from collections import deque
from pathlib import Path

from groundtruth.core.enums import EventType
from groundtruth.core.pack import DomainPack, load_pack
from groundtruth.core.projector import append_and_project
from groundtruth.core.trust_service import recompute_trust


def get_downstream_children(conn: sqlite3.Connection, parent_id: str) -> list[str]:
    """Retrieve direct child fact IDs derived from parent_id."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT child_id FROM fact_edges WHERE parent_id = ? ORDER BY child_id ASC",
        (parent_id,),
    )
    return [row["child_id"] for row in cursor.fetchall()]


def propagate_taint(
    conn: sqlite3.Connection,
    case_id: str,
    root_fact_id: str,
    actor: str = "system",
    pack: DomainPack | None = None,
) -> set[str]:
    """Recursively cascade taint downstream from an invalidated root fact (INV-9).

    Walks fact_edges child links BFS.
    For every descendant, emits FACT_TAINTED event setting status to TAINTED.
    Recomputes trust across the case DAG (tainted facts count as 0 trust).
    Returns the set of tainted descendant fact IDs.
    """
    queue: deque[str] = deque(get_downstream_children(conn, root_fact_id))
    tainted: set[str] = set()

    while queue:
        child_id = queue.popleft()
        if child_id in tainted or child_id == root_fact_id:
            continue
        tainted.add(child_id)

        # Emit FACT_TAINTED event for this descendant
        append_and_project(
            conn=conn,
            case_id=case_id,
            event_type=EventType.FACT_TAINTED,
            actor=actor,
            payload={
                "fact_id": child_id,
                "root_cause_fact_id": root_fact_id,
                "reason": f"tainted_by_ancestor:{root_fact_id}",
            },
        )

        # Queue descendants of this child
        for next_child in get_downstream_children(conn, child_id):
            if next_child not in tainted:
                queue.append(next_child)

    # Recompute trust across the case
    active_pack = pack
    if active_pack is None:
        cursor = conn.cursor()
        cursor.execute("SELECT domain_pack FROM cases WHERE case_id = ?", (case_id,))
        row = cursor.fetchone()
        if row and row["domain_pack"]:
            active_pack = load_pack(Path("groundtruth/packs") / row["domain_pack"])

    if active_pack is not None:
        recompute_trust(
            conn=conn,
            case_id=case_id,
            pack=active_pack,
            cause_event_id=f"taint_cascade_{root_fact_id}",
        )

    return tainted


def retract_and_taint(
    conn: sqlite3.Connection,
    case_id: str,
    fact_id: str,
    actor: str = "system",
    reason: str = "retraction",
    pack: DomainPack | None = None,
) -> set[str]:
    """Retract a root premise and cascade taint to all downstream descendants."""
    # Retract root fact via FACT_DOWNGRADED with retract=True
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.FACT_DOWNGRADED,
        actor=actor,
        payload={
            "fact_id": fact_id,
            "reason": reason,
            "retract": True,
        },
    )

    # Propagate taint cascade to all descendants
    return propagate_taint(
        conn=conn,
        case_id=case_id,
        root_fact_id=fact_id,
        actor=actor,
        pack=pack,
    )
