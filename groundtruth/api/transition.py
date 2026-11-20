"""Case State Transitions API Endpoint.

Enforces:
- CASE-2: Transitions emit CASE_STATE_CHANGED events.
  Requested through /transition by an orchestrator or human token.
  concluded_at is set from event timestamp when new state is CONCLUDED.
- CASE-3: A CLOSED case's ledger is frozen. Subsequent attempts go to access_log.
- SEC-2: A token stops working when its case is CLOSED.
- SEC-7: Only orchestrator or human roles may call /transition.
- Architecture Section 12 (POST /cases/{id}/transition).
"""

import sqlite3

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from groundtruth.api.auth import resolve_caller
from groundtruth.api.cases import get_db
from groundtruth.core.enums import CaseState, EventType
from groundtruth.core.projector import append_and_project, load_case_projection

router = APIRouter(prefix="/cases", tags=["lifecycle"])

LEGAL_TRANSITIONS: dict[str, list[str]] = {
    CaseState.OPEN.value: [CaseState.INVESTIGATING.value],
    CaseState.INVESTIGATING.value: [CaseState.CONCLUDED.value],
    CaseState.CONCLUDED.value: [CaseState.CLOSED.value],
    CaseState.CLOSED.value: [],
}


class TransitionRequest(BaseModel):
    """Payload specifying the target case state."""

    to: str = Field(description="Target state: OPEN, INVESTIGATING, CONCLUDED, CLOSED")


class TransitionResponse(BaseModel):
    """Result of a state transition."""

    case_id: str
    state: str
    event_id: str
    concluded_at: str | None = None


@router.post("/{case_id}/transition", response_model=TransitionResponse)
def transition_case(
    case_id: str,
    req: TransitionRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> TransitionResponse:
    """Transition a case's state in the append-only ledger (CASE-2, SEC-7)."""
    # 1. Authenticate caller and enforce case isolation
    caller = resolve_caller(
        conn=conn,
        authorization=authorization,
        target_case_id=case_id,
        endpoint_path=request.url.path,
    )

    # 2. Enforce role permission (SEC-7): orchestrator or human only
    if caller.role not in ("orchestrator", "human"):
        raise HTTPException(
            status_code=403,
            detail=(
                f"Role '{caller.role}' not permitted to call /transition "
                "(orchestrator or human required)"
            ),
        )

    # 3. Load current case state
    state = load_case_projection(conn, case_id)
    if not state.case:
        raise HTTPException(status_code=404, detail="Case not found")

    current_state = state.case.state
    target_state = req.to.strip().upper()

    # Validate target state exists in enum
    valid_states = [s.value for s in CaseState]
    if target_state not in valid_states:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target state '{req.to}'. Must be one of {valid_states}",
        )

    # 4. Enforce legal transition sequence (CASE-2)
    allowed_targets = LEGAL_TRANSITIONS.get(current_state, [])
    if target_state not in allowed_targets:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid state transition from '{current_state}' to '{target_state}'. "
            f"Allowed transitions from '{current_state}': {allowed_targets}",
        )

    # 5. Append CASE_STATE_CHANGED event through single write path (INV-3)
    event = append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.CASE_STATE_CHANGED,
        actor=caller.role,
        payload={
            "from": current_state,
            "to": target_state,
        },
    )

    # 6. Reload updated projection state
    updated_state = load_case_projection(conn, case_id)
    assert updated_state.case is not None

    return TransitionResponse(
        case_id=case_id,
        state=updated_state.case.state,
        event_id=event.event_id,
        concluded_at=updated_state.case.concluded_at,
    )
