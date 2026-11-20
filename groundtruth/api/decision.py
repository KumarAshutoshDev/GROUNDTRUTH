"""Case Decision API Endpoint for Orchestrator.

Enforces:
- Architecture Section 12 & Section 13 (GET /cases/{id}/decision).
- CASE-4: Returns ESCALATE when budget is exhausted.
- Pure deterministic signal: AUTO_FIX, ESCALATE, or NEED_MORE.
"""

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from groundtruth.api.auth import resolve_caller
from groundtruth.api.cases import get_db
from groundtruth.core.decision import evaluate_decision
from groundtruth.core.pack import load_pack
from groundtruth.core.projector import load_case_projection

router = APIRouter(prefix="/cases", tags=["decision"])


class DecisionResponse(BaseModel):
    """Decision output governing the orchestrator dispatch loop."""

    signal: str = Field(description="AUTO_FIX, ESCALATE, or NEED_MORE")
    reasons: list[str] = Field(default_factory=list, description="Explanations for the signal")
    missing_checks: list[str] = Field(
        default_factory=list, description="Fact types or checks required before concluding"
    )
    rework_queue: list[str] = Field(
        default_factory=list, description="Contested or invalidated facts requiring investigation"
    )
    conclusion_fact_id: str | None = Field(
        default=None, description="Pointer to admitted conclusion fact"
    )


@router.get("/{case_id}/decision", response_model=DecisionResponse)
def get_decision(
    case_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> DecisionResponse:
    """Evaluate deterministic decision rules for a case (INV-6, Architecture 13)."""
    caller = resolve_caller(
        conn=conn,
        authorization=authorization,
        target_case_id=case_id,
        endpoint_path=request.url.path,
    )

    # Orchestrator or human token only (Architecture 11)
    if caller.role not in ("orchestrator", "human"):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{caller.role}' not permitted to call /decision",
        )

    state = load_case_projection(conn, case_id)
    if not state.case:
        raise HTTPException(status_code=404, detail="Case not found")

    pack_dir = Path("groundtruth/packs") / state.case.domain_pack
    pack = load_pack(pack_dir)

    # Evaluate deterministic decision rules (INV-6, rules Section 3.5)
    res = evaluate_decision(conn=conn, case_id=case_id, pack=pack)

    return DecisionResponse(
        signal=res.signal,
        reasons=res.reasons,
        missing_checks=res.missing_checks,
        rework_queue=res.rework_queue,
        conclusion_fact_id=res.conclusion_fact_id,
    )
