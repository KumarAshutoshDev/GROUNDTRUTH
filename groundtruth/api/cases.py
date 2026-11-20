"""Case lifecycle and historical state inspection endpoints."""

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from groundtruth.api.auth import issue_case_tokens, verify_bootstrap_key
from groundtruth.core.enums import EventType
from groundtruth.core.pack import load_pack, seed_contracts
from groundtruth.core.projector import append_and_project, load_case_projection
from groundtruth.core.replay import replay_case
from groundtruth.core.trust_service import apply_decay_tick
from groundtruth.core.utils import Clock, SystemClock, UUIDGenerator

router = APIRouter(prefix="/cases", tags=["cases"])


class CreateCaseRequest(BaseModel):
    domain_pack: str
    trigger: dict[str, Any]


class CreateCaseResponse(BaseModel):
    case_id: str
    domain_pack: str
    state: str
    opened_at: str
    concluded_at: str | None = None
    conclusion_fact_id: str | None = None
    tokens: dict[str, str]


class CaseSummaryResponse(BaseModel):
    case_id: str
    domain_pack: str
    trigger: dict[str, Any] = Field(default_factory=dict)
    state: str
    opened_at: str
    concluded_at: str | None = None
    conclusion_fact_id: str | None = None


# Module-level connection dependency placeholder (overridden by app or test)
def get_db() -> sqlite3.Connection:
    raise NotImplementedError("Database dependency not configured")


def get_clock() -> Clock:
    """Dependency provider for system or fixture clock."""
    return SystemClock()


@router.post("", response_model=CreateCaseResponse)
def create_case(
    request: CreateCaseRequest,
    x_bootstrap_key: str | None = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> CreateCaseResponse:
    """Open a new investigation case, seed contracts, and issue case-scoped tokens."""
    # Verify bootstrap key (SEC-4)
    verify_bootstrap_key(x_bootstrap_key)

    pack_dir = Path("groundtruth/packs") / request.domain_pack
    if not pack_dir.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Domain pack '{request.domain_pack}' not found",
        )

    pack = load_pack(pack_dir)
    seed_contracts(conn, pack)

    id_gen = UUIDGenerator()
    case_id = id_gen.generate("case")

    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.CASE_OPENED,
        actor="system",
        payload={"domain_pack": request.domain_pack, "trigger": request.trigger},
    )

    state = load_case_projection(conn, case_id)
    if not state.case:
        raise HTTPException(status_code=500, detail="Failed to open case")

    tokens = issue_case_tokens(conn, case_id, pack)

    return CreateCaseResponse(
        case_id=state.case.case_id,
        domain_pack=state.case.domain_pack,
        state=state.case.state,
        opened_at=state.case.opened_at,
        concluded_at=state.case.concluded_at,
        conclusion_fact_id=state.case.conclusion_fact_id,
        tokens=tokens,
    )


@router.get("", response_model=list[CaseSummaryResponse])
def list_cases(
    conn: sqlite3.Connection = Depends(get_db),
) -> list[CaseSummaryResponse]:
    """List all cases sorted by opened_at descending."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT case_id, domain_pack, trigger, state, opened_at, concluded_at, conclusion_fact_id
        FROM cases
        ORDER BY opened_at DESC
        """
    )
    rows = cursor.fetchall()
    results: list[CaseSummaryResponse] = []
    for row in rows:
        trig = row["trigger"]
        trig_dict = json.loads(trig) if isinstance(trig, str) else (trig or {})
        results.append(
            CaseSummaryResponse(
                case_id=row["case_id"],
                domain_pack=row["domain_pack"],
                trigger=trig_dict,
                state=row["state"],
                opened_at=row["opened_at"],
                concluded_at=row["concluded_at"],
                conclusion_fact_id=row["conclusion_fact_id"],
            )
        )
    return results


@router.get("/{case_id}", response_model=CaseSummaryResponse)
def get_case(
    case_id: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> CaseSummaryResponse:
    """Get current case summary and conclusion pointer."""
    state = load_case_projection(conn, case_id)
    if not state.case:
        raise HTTPException(status_code=404, detail="Case not found")

    return CaseSummaryResponse(
        case_id=state.case.case_id,
        domain_pack=state.case.domain_pack,
        trigger=state.case.trigger,
        state=state.case.state,
        opened_at=state.case.opened_at,
        concluded_at=state.case.concluded_at,
        conclusion_fact_id=state.case.conclusion_fact_id,
    )


@router.get("/{case_id}/events")
def get_events(
    case_id: str,
    upto: int | None = Query(default=None, ge=1),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get ledger events up to sequence N for replay and audit."""
    cursor = conn.cursor()
    if upto is not None:
        cursor.execute(
            """
            SELECT event_id, case_id, seq, event_type, actor, payload, prev_hash, hash, ts
            FROM events
            WHERE case_id = ? AND seq <= ?
            ORDER BY seq ASC
            """,
            (case_id, upto),
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

    import json

    events = []
    for row in cursor.fetchall():
        payload_val = row["payload"]
        try:
            payload_dict = json.loads(payload_val) if isinstance(payload_val, str) else payload_val
        except Exception:
            payload_dict = {}

        events.append(
            {
                "event_id": row["event_id"],
                "case_id": row["case_id"],
                "seq": row["seq"],
                "event_type": row["event_type"],
                "actor": row["actor"],
                "payload": payload_dict,
                "prev_hash": row["prev_hash"],
                "hash": row["hash"],
                "ts": row["ts"],
            }
        )

    return events


@router.get("/{case_id}/state")
def get_state(
    case_id: str,
    at: int | None = Query(default=None, ge=1),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Get reconstructed fact state at event sequence N."""
    if at is not None:
        case_state = replay_case(conn, case_id, upto_seq=at)
    else:
        # TRUST-8: Decay tick runs for current state, never for historical at=N
        apply_decay_tick(conn=conn, case_id=case_id)
        case_state = load_case_projection(conn, case_id)

    if not case_state.case and not case_state.facts:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM events WHERE case_id = ? LIMIT 1", (case_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")

    return {
        "case_id": case_state.case_id,
        "case": case_state.case.__dict__ if case_state.case else None,
        "facts": {fid: f.__dict__ for fid, f in case_state.facts.items()},
        "edges": [{"child_id": e.child_id, "parent_id": e.parent_id} for e in case_state.edges],
        "negative_checks": {cid: n.__dict__ for cid, n in case_state.negative_checks.items()},
    }
