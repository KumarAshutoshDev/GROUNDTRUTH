"""Negative Knowledge API Endpoints (Architecture Section 12, F6, NEG-1..3).

Provides:
- POST /cases/{id}/negative/query: query negative checks to suppress duplicate work.
- POST /cases/{id}/negative: submit negative check fact proposal through Write Gate pipeline.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from groundtruth.adapters.llm import LLMAdapter, get_default_adapter
from groundtruth.api.auth import resolve_caller
from groundtruth.api.cases import get_db
from groundtruth.core.budget import calculate_budget_usage
from groundtruth.core.enums import GateVerdict, SourceType
from groundtruth.core.gate import FactProposal, evaluate_proposal
from groundtruth.core.negative import NegativeCheckSpec, check_negative
from groundtruth.core.pack import load_pack
from groundtruth.core.projector import load_case_projection

router = APIRouter(prefix="/cases", tags=["negative"])

_default_verifier_adapter: LLMAdapter | None = None


def get_verifier_adapter() -> LLMAdapter:
    """Dependency provider for the LLM adapter used by verifier."""
    global _default_verifier_adapter
    if _default_verifier_adapter is not None:
        return _default_verifier_adapter
    return get_default_adapter()


class NegativeQueryRequest(BaseModel):
    """Query payload asking whether a check is already covered by negative knowledge."""

    check_type: str = Field(description="Check identifier, e.g. oom_killed")
    scope: list[str] = Field(description="List of entities to check, e.g. pod names")
    window_start: str | None = Field(default=None, description="Start of check window (ISO 8601)")
    window_end: str | None = Field(default=None, description="End of check window (ISO 8601)")
    window: dict[str, str] | None = Field(
        default=None, description="Optional dict window with start/end or window_start/window_end"
    )
    expires_at: str | None = Field(
        default=None, description="Optional expiry timestamp for check freshness"
    )


class NegativeQueryResponse(BaseModel):
    """Response indicating whether the check is COVERED or NOT_COVERED."""

    verdict: str = Field(description="COVERED or NOT_COVERED")
    reason: str = Field(description="COVERED or exact failing condition")
    status: str = Field(description="Formatted verdict:reason status")
    matching_fact_id: str | None = Field(default=None, description="Fact ID providing coverage")
    matching_check_id: str | None = Field(default=None, description="Negative check ID")


class NegativeRecordRequest(BaseModel):
    """Payload to record a ruled-out negative check through Write Gate."""

    check_type: str = Field(description="Check identifier, e.g. oom_killed")
    scope: list[str] = Field(description="List of entities verified, e.g. pod names")
    window_start: str | None = Field(default=None, description="Start of check window")
    window_end: str | None = Field(default=None, description="End of check window")
    window: dict[str, str] | None = Field(default=None, description="Optional dict window")
    expires_at: str | None = Field(default=None, description="Optional expiry timestamp")
    evidence_ref: str | None = Field(default=None, description="Log pointer or evidence reference")
    self_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_type: SourceType = Field(default=SourceType.TOOL_OUTPUT)
    derived_from: list[str] = Field(default_factory=list)


class NegativeRecordResponse(BaseModel):
    """Outcome of submitting negative check proposal through Write Gate."""

    verdict: GateVerdict
    reason: str
    fact_id: str
    own_trust: float
    effective_trust: float
    status: str | None = None


@router.post("/{case_id}/negative/query", response_model=NegativeQueryResponse)
def query_negative(
    case_id: str,
    query_req: NegativeQueryRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> NegativeQueryResponse:
    """Evaluate whether requested check is covered by existing negative knowledge."""
    _caller = resolve_caller(
        conn=conn,
        target_case_id=case_id,
        endpoint_path=request.url.path,
        authorization=authorization,
    )

    state = load_case_projection(conn, case_id)
    if not state.case:
        raise HTTPException(status_code=404, detail="Case not found")

    pack_dir = Path("groundtruth/packs") / state.case.domain_pack
    pack = load_pack(pack_dir)

    # Budget exhaustion check (CASE-4)
    usage = calculate_budget_usage(conn, case_id, pack)
    if usage.is_exhausted:
        raise HTTPException(
            status_code=429,
            detail=f"BUDGET_EXHAUSTED: {usage.exhaustion_reason}",
        )

    # Resolve window
    w_start = query_req.window_start or (
        (query_req.window.get("start") or query_req.window.get("window_start"))
        if query_req.window
        else ""
    )
    w_end = query_req.window_end or (
        (query_req.window.get("end") or query_req.window.get("window_end"))
        if query_req.window
        else ""
    )

    spec = NegativeCheckSpec(
        check_type=query_req.check_type,
        scope=query_req.scope,
        window_start=w_start or "",
        window_end=w_end or "",
        expires_at=query_req.expires_at,
    )

    result = check_negative(conn=conn, case_id=case_id, query=spec, pack=pack)

    return NegativeQueryResponse(
        verdict=result.verdict,
        reason=result.reason,
        status=result.status,
        matching_fact_id=result.matching_fact_id,
        matching_check_id=result.matching_check_id,
    )


@router.post("/{case_id}/negative", response_model=NegativeRecordResponse)
def record_negative(
    case_id: str,
    record_req: NegativeRecordRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
    adapter: LLMAdapter = Depends(get_verifier_adapter),
) -> NegativeRecordResponse:
    """Submit a negative check assertion through Write Gate pipeline (INV-3, F6)."""
    caller = resolve_caller(
        conn=conn,
        target_case_id=case_id,
        endpoint_path=request.url.path,
        authorization=authorization,
    )

    state = load_case_projection(conn, case_id)
    if not state.case:
        raise HTTPException(status_code=404, detail="Case not found")

    pack_dir = Path("groundtruth/packs") / state.case.domain_pack
    pack = load_pack(pack_dir)

    # Budget exhaustion check (CASE-4)
    usage = calculate_budget_usage(conn, case_id, pack)
    if usage.is_exhausted:
        raise HTTPException(
            status_code=429,
            detail=f"BUDGET_EXHAUSTED: {usage.exhaustion_reason}",
        )

    w_start = record_req.window_start or (
        (record_req.window.get("start") or record_req.window.get("window_start"))
        if record_req.window
        else ""
    )
    w_end = record_req.window_end or (
        (record_req.window.get("end") or record_req.window.get("window_end"))
        if record_req.window
        else ""
    )

    fact_val: dict[str, Any] = {
        "check_type": record_req.check_type,
        "scope": record_req.scope,
        "window_start": w_start,
        "window_end": w_end,
    }
    if record_req.expires_at:
        fact_val["expires_at"] = record_req.expires_at

    proposal = FactProposal(
        type="negative_check",
        value=fact_val,
        source=caller.agent_id,
        source_type=record_req.source_type,
        self_confidence=record_req.self_confidence,
        evidence_ref=record_req.evidence_ref,
        derived_from=record_req.derived_from,
    )

    gate_res = evaluate_proposal(
        conn=conn,
        case_id=case_id,
        caller_role=caller.role,
        proposal=proposal,
        pack=pack,
        verifier_adapter=adapter,
    )

    status_str = (
        "ADMIT"
        if gate_res.verdict == GateVerdict.ADMIT
        else f"{gate_res.verdict}:{gate_res.reason}"
    )

    return NegativeRecordResponse(
        verdict=gate_res.verdict,
        reason=gate_res.reason,
        fact_id=gate_res.fact_id,
        own_trust=gate_res.own_trust,
        effective_trust=gate_res.effective_trust,
        status=status_str,
    )
