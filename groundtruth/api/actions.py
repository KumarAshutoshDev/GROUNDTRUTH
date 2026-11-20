"""Agent Actions and Budget Accounting API.

Enforces:
- CASE-4: Case budget accounting via AGENT_ACTION events.
- Architecture Section 4.6 and Section 12 (POST /cases/{id}/actions).
"""

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from groundtruth.api.auth import resolve_caller
from groundtruth.api.cases import get_db
from groundtruth.core.budget import (
    BudgetUsage,
    calculate_budget_usage,
    record_agent_action,
)
from groundtruth.core.pack import load_pack
from groundtruth.core.projector import load_case_projection

router = APIRouter(prefix="/cases", tags=["actions"])


class ActionRequest(BaseModel):
    """Payload submitted by agent after executing a tool call."""

    tool: str = Field(min_length=1, description="Tool name executed by agent")
    args_hash: str = Field(min_length=1, description="Hash of arguments passed to tool")
    result_hash: str = Field(min_length=1, description="Hash of tool execution output")
    tokens_in: int = Field(default=0, ge=0, description="Tokens in prompt/query")
    tokens_out: int = Field(default=0, ge=0, description="Tokens in response/output")
    cache_hit: bool = Field(default=False, description="Whether tool execution hit a cache")


class ActionResponse(BaseModel):
    """Response returning recorded action event ID and updated case budget usage."""

    event_id: str
    usage: BudgetUsage


@router.post("/{case_id}/actions", response_model=ActionResponse)
def record_action(
    case_id: str,
    req: ActionRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> ActionResponse:
    """Record an agent tool call (AGENT_ACTION) and return updated budget usage (CASE-4)."""
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

    # Check budget before executing (stops next call if already exhausted)
    current_usage = calculate_budget_usage(conn, case_id, pack)
    if current_usage.is_exhausted:
        raise HTTPException(
            status_code=429,
            detail=f"BUDGET_EXHAUSTED: {current_usage.exhaustion_reason}",
        )

    # Record the AGENT_ACTION event in the append-only ledger
    event = record_agent_action(
        conn=conn,
        case_id=case_id,
        actor=caller.role,
        tool=req.tool,
        args_hash=req.args_hash,
        result_hash=req.result_hash,
        tokens_in=req.tokens_in,
        tokens_out=req.tokens_out,
        cache_hit=req.cache_hit,
    )

    # Calculate updated budget usage after recording
    updated_usage = calculate_budget_usage(conn, case_id, pack)

    return ActionResponse(
        event_id=event.event_id,
        usage=updated_usage,
    )
