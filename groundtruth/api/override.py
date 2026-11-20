"""Human Administrative Override API Endpoint (SEC-3, INV-9, DASH-1).

Enforces:
- SEC-3: Reserved 'human' role token required; agent tokens are forbidden (403).
- INV-9: Manual un-tainting (RESTORE_ACTIVE), force retraction (FORCE_RETRACT),
  or trust adjustment (ADJUST_TRUST).
- Validates reason is non-empty and logs all human actions to append-only ledger.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from groundtruth.api.auth import resolve_caller
from groundtruth.api.cases import get_db
from groundtruth.core.decision import evaluate_decision
from groundtruth.core.enums import EventType
from groundtruth.core.pack import load_pack
from groundtruth.core.projector import append_and_project, load_case_projection
from groundtruth.core.taint import propagate_taint
from groundtruth.core.trust_service import recompute_trust

router = APIRouter(prefix="/cases", tags=["override"])


class HumanOverrideRequest(BaseModel):
    """Payload for human administrative override."""

    fact_id: str = Field(description="Target fact ID to override")
    action: str = Field(
        description="Override action: RESTORE_ACTIVE, FORCE_RETRACT, or ADJUST_TRUST"
    )
    reason: str = Field(description="Mandatory human explanation for audit log")
    own_trust: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Optional or required trust score"
    )


class HumanOverrideResponse(BaseModel):
    """Result of human override operation."""

    fact_id: str
    status: str
    own_trust: float
    effective_trust: float
    decision_signal: str
    rework_queue: list[str]


@router.post("/{case_id}/override", response_model=HumanOverrideResponse)
def apply_override(
    case_id: str,
    override_req: HumanOverrideRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> HumanOverrideResponse:
    """Execute administrative override on a case fact (SEC-3, INV-9)."""
    # 1. Authenticate caller (SEC-3: human role only)
    caller = resolve_caller(
        conn=conn,
        target_case_id=case_id,
        endpoint_path=request.url.path,
        authorization=authorization,
    )

    if caller.role != "human":
        raise HTTPException(
            status_code=403,
            detail=(
                f"Role '{caller.role}' not permitted to call /override: "
                "reserved for 'human' role (SEC-3)"
            ),
        )

    # 2. Validate reason is non-empty
    if not override_req.reason or not override_req.reason.strip():
        raise HTTPException(
            status_code=422,
            detail="Override reason must not be empty",
        )

    # 3. Validate action
    valid_actions = {"RESTORE_ACTIVE", "FORCE_RETRACT", "ADJUST_TRUST"}
    if override_req.action not in valid_actions:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid override action '{override_req.action}'. Allowed: {valid_actions}",
        )

    # 4. Load case and verify fact exists
    state = load_case_projection(conn, case_id)
    if not state.case:
        raise HTTPException(status_code=404, detail="Case not found")

    fact = state.facts.get(override_req.fact_id)
    if not fact:
        raise HTTPException(
            status_code=404,
            detail=f"Fact '{override_req.fact_id}' not found in case '{case_id}'",
        )

    pack_dir = Path("groundtruth/packs") / state.case.domain_pack
    pack = load_pack(pack_dir)

    # 5. Handle action
    if override_req.action == "RESTORE_ACTIVE":
        target_own = (
            override_req.own_trust
            if override_req.own_trust is not None
            else (fact.self_confidence or 1.0)
        )
        append_and_project(
            conn=conn,
            case_id=case_id,
            event_type=EventType.HUMAN_OVERRIDE,
            actor=caller.agent_id,
            payload={
                "fact_id": override_req.fact_id,
                "action": "RESTORE_ACTIVE",
                "reason": override_req.reason.strip(),
                "own_trust": target_own,
            },
        )
        recompute_trust(
            conn=conn,
            case_id=case_id,
            pack=pack,
            cause_event_id=f"override_restore_{override_req.fact_id}",
        )

    elif override_req.action == "FORCE_RETRACT":
        append_and_project(
            conn=conn,
            case_id=case_id,
            event_type=EventType.HUMAN_OVERRIDE,
            actor=caller.agent_id,
            payload={
                "fact_id": override_req.fact_id,
                "action": "FORCE_RETRACT",
                "reason": override_req.reason.strip(),
            },
        )
        propagate_taint(
            conn=conn,
            case_id=case_id,
            root_fact_id=override_req.fact_id,
            actor=caller.agent_id,
            pack=pack,
        )

    elif override_req.action == "ADJUST_TRUST":
        if override_req.own_trust is None:
            raise HTTPException(
                status_code=422,
                detail="own_trust must be provided for ADJUST_TRUST action",
            )
        append_and_project(
            conn=conn,
            case_id=case_id,
            event_type=EventType.HUMAN_OVERRIDE,
            actor=caller.agent_id,
            payload={
                "fact_id": override_req.fact_id,
                "action": "ADJUST_TRUST",
                "reason": override_req.reason.strip(),
                "own_trust": override_req.own_trust,
            },
        )
        recompute_trust(
            conn=conn,
            case_id=case_id,
            pack=pack,
            cause_event_id=f"override_adjust_{override_req.fact_id}",
        )

    # 6. Re-evaluate decision
    updated_state = load_case_projection(conn, case_id)
    updated_fact = updated_state.facts[override_req.fact_id]
    decision = evaluate_decision(conn=conn, case_id=case_id, pack=pack)

    return HumanOverrideResponse(
        fact_id=updated_fact.fact_id,
        status=updated_fact.status,
        own_trust=updated_fact.own_trust,
        effective_trust=updated_fact.effective_trust,
        decision_signal=decision.signal,
        rework_queue=decision.rework_queue,
    )
