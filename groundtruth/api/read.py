"""Read-side context projection API endpoint.

Enforces:
- FR-5: Role-scoped context projection.
- INV-10: Cross-case & out-of-contract read attempts append ACCESS_DENIED to ledger and return 403.
- CASE-4: Budget check returns 429 when budget is exhausted.
- Architecture Section 10 and Section 12 (POST /cases/{id}/read).
"""

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from groundtruth.api.auth import resolve_caller
from groundtruth.api.cases import get_db
from groundtruth.core.budget import calculate_budget_usage
from groundtruth.core.enums import EventType
from groundtruth.core.pack import load_pack
from groundtruth.core.projection import ContextProjection, project_context
from groundtruth.core.projector import append_and_project, load_case_projection
from groundtruth.core.trust_service import apply_decay_tick

router = APIRouter(prefix="/cases", tags=["read"])


class ReadRequest(BaseModel):
    """Request payload for reading role-scoped case context."""

    goal: str = Field(default="", description="Current agent goal or inquiry")
    fact_type: str | None = Field(default=None, description="Optional single fact type filter")


@router.post("/{case_id}/read", response_model=ContextProjection)
def read_context(
    case_id: str,
    req: ReadRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> ContextProjection:
    """Read projected case context filtered by caller's role contract (FR-5, INV-10)."""
    # 1. Authenticate caller and enforce case isolation (INV-10)
    caller = resolve_caller(
        conn=conn,
        authorization=authorization,
        target_case_id=case_id,
        endpoint_path=request.url.path,
    )

    state = load_case_projection(conn, case_id)
    if not state.case:
        raise HTTPException(status_code=404, detail="Case not found")

    pack_dir = Path("groundtruth/packs") / state.case.domain_pack
    pack = load_pack(pack_dir)

    # 2. Check budget (CASE-4)
    usage = calculate_budget_usage(conn, case_id, pack)
    if usage.is_exhausted:
        raise HTTPException(
            status_code=429,
            detail=f"BUDGET_EXHAUSTED: {usage.exhaustion_reason}",
        )

    # TRUST-8: Decay tick before /read
    apply_decay_tick(conn=conn, case_id=case_id, pack=pack)

    # 3. Check role contract reads permission (INV-10)
    contract = pack.contracts.get(caller.role)
    if not contract or (not contract.reads and "*" not in contract.reads):
        append_and_project(
            conn=conn,
            case_id=caller.case_id,
            event_type=EventType.ACCESS_DENIED,
            actor=caller.agent_id,
            payload={
                "attempted_case_id": case_id,
                "endpoint": request.url.path,
                "role": caller.role,
                "reason": "out_of_contract_read_no_reads",
            },
        )
        raise HTTPException(
            status_code=403,
            detail=f"Role '{caller.role}' contract has no read permissions (reads: [])",
        )

    if req.fact_type and "*" not in contract.reads and req.fact_type not in contract.reads:
        append_and_project(
            conn=conn,
            case_id=caller.case_id,
            event_type=EventType.ACCESS_DENIED,
            actor=caller.agent_id,
            payload={
                "attempted_case_id": case_id,
                "endpoint": request.url.path,
                "role": caller.role,
                "reason": f"out_of_contract_read_type_{req.fact_type}",
            },
        )
        raise HTTPException(
            status_code=403,
            detail=f"Role '{caller.role}' cannot read fact type '{req.fact_type}' outside contract",
        )

    # 4. Project context
    try:
        return project_context(
            conn=conn,
            role=caller.role,
            case_id=case_id,
            goal=req.goal,
            pack=pack,
            fact_type_filter=req.fact_type,
        )
    except PermissionError as e:
        append_and_project(
            conn=conn,
            case_id=caller.case_id,
            event_type=EventType.ACCESS_DENIED,
            actor=caller.agent_id,
            payload={
                "attempted_case_id": case_id,
                "endpoint": request.url.path,
                "role": caller.role,
                "reason": str(e),
            },
        )
        raise HTTPException(status_code=403, detail=str(e)) from e
