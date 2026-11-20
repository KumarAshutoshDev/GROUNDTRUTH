"""Proposal and re-verification endpoints for GroundTruth.

Enforces:
- INV-3: Writes go through Write Gate pipeline.
- INV-5: Identity bound to token.
- REVERIFY-1: Re-verification restricted to orchestrator or human role;
  an overturning result emits FACT_DOWNGRADED.
"""

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from groundtruth.adapters.llm import LLMAdapter, MockFixtureLLMAdapter
from groundtruth.api.auth import resolve_caller
from groundtruth.api.cases import get_db
from groundtruth.core.budget import calculate_budget_usage
from groundtruth.core.enums import EventType, GateVerdict
from groundtruth.core.gate import FactProposal, evaluate_proposal
from groundtruth.core.pack import load_pack
from groundtruth.core.projector import append_and_project, load_case_projection
from groundtruth.core.taint import propagate_taint
from groundtruth.core.verifier import verify_claim

router = APIRouter(prefix="/cases", tags=["proposals"])

# Adapter provider (can be overridden in tests or configured with ProviderLLMAdapter)
_default_verifier_adapter: LLMAdapter = MockFixtureLLMAdapter()


def get_verifier_adapter() -> LLMAdapter:
    return _default_verifier_adapter


class ProposeResponse(BaseModel):
    verdict: GateVerdict
    reason: str
    fact_id: str
    own_trust: float
    effective_trust: float


class ReverifyRequest(BaseModel):
    fact_id: str
    retract: bool = True


class ReverifyResponse(BaseModel):
    fact_id: str
    status: str
    verifier_state: str
    overturned: bool
    rationale: str | None = None


@router.post("/{case_id}/propose", response_model=ProposeResponse)
def propose_fact(
    case_id: str,
    proposal: FactProposal,
    request: Request,
    authorization: str | None = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
    adapter: LLMAdapter = Depends(get_verifier_adapter),
) -> ProposeResponse:
    """Submit a factual assertion or inference through the Write Gate."""
    # 1. Resolve token and authenticate caller (INV-5, INV-10, SEC-5)
    caller = resolve_caller(
        conn=conn,
        target_case_id=case_id,
        endpoint_path=request.url.path,
        authorization=authorization,
    )

    # 2. Load case and pack
    state = load_case_projection(conn, case_id)
    if not state.case:
        raise HTTPException(status_code=404, detail="Case not found")

    pack_dir = Path("groundtruth/packs") / state.case.domain_pack
    pack = load_pack(pack_dir)

    # Check budget exhaustion (CASE-4)
    usage = calculate_budget_usage(conn, case_id, pack)
    if usage.is_exhausted:
        raise HTTPException(
            status_code=429,
            detail=f"BUDGET_EXHAUSTED: {usage.exhaustion_reason}",
        )

    # 3. Log FACT_PROPOSED event (audit only, zero reducer ops)
    proposal_dict = proposal.model_dump()
    proposal_dict["agent_id"] = caller.agent_id  # Enforce INV-5: bind agent_id to token

    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.FACT_PROPOSED,
        actor=caller.agent_id,
        payload={"proposed_fact": proposal_dict},
    )

    # 4. Evaluate proposal through Write Gate pipeline
    result = evaluate_proposal(
        conn=conn,
        case_id=case_id,
        caller_role=caller.role,
        proposal=proposal,
        pack=pack,
        verifier_adapter=adapter,
    )

    return ProposeResponse(
        verdict=result.verdict,
        reason=result.reason,
        fact_id=result.fact_id,
        own_trust=result.own_trust,
        effective_trust=result.effective_trust,
    )


@router.post("/{case_id}/reverify", response_model=ReverifyResponse)
def reverify_fact(
    case_id: str,
    req: ReverifyRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
    adapter: LLMAdapter = Depends(get_verifier_adapter),
) -> ReverifyResponse:
    """Re-run adversarial verification on an admitted fact (REVERIFY-1)."""
    caller = resolve_caller(
        conn=conn,
        target_case_id=case_id,
        endpoint_path=request.url.path,
        authorization=authorization,
    )

    # SEC-7 & REVERIFY-1: Orchestrator or human token only
    if caller.role not in ("orchestrator", "human"):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{caller.role}' not permitted to call /reverify",
        )

    state = load_case_projection(conn, case_id)
    fact = state.facts.get(req.fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail=f"Fact '{req.fact_id}' not found")

    # Re-run verifier
    evidence_content = f"Re-verification of evidence: {fact.evidence_ref or 'ancestor references'}"
    v_output = verify_claim(
        claim_data={"value": fact.value},
        evidence_content=evidence_content,
        adapter=adapter,
    )

    if v_output.verdict != "SUPPORTED":
        # Overturned: emit FACT_DOWNGRADED (REVERIFY-1)
        append_and_project(
            conn=conn,
            case_id=case_id,
            event_type=EventType.FACT_DOWNGRADED,
            actor=caller.agent_id,
            payload={
                "fact_id": req.fact_id,
                "verifier_output": v_output.model_dump(),
                "reason": f"reverification_overturned: {v_output.rationale}",
                "retract": req.retract,
            },
        )
        if req.retract:
            propagate_taint(
                conn=conn,
                case_id=case_id,
                root_fact_id=req.fact_id,
                actor=caller.agent_id,
            )

        updated_state = load_case_projection(conn, case_id)
        updated_fact = updated_state.facts[req.fact_id]
        return ReverifyResponse(
            fact_id=req.fact_id,
            status=updated_fact.status,
            verifier_state=updated_fact.verifier_state,
            overturned=True,
            rationale=v_output.rationale,
        )

    return ReverifyResponse(
        fact_id=req.fact_id,
        status=fact.status,
        verifier_state=fact.verifier_state,
        overturned=False,
        rationale=v_output.rationale,
    )
