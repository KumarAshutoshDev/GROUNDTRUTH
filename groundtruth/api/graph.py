"""Causality Graph Query API Endpoint.

Enforces:
- FR-7: Causality graph endpoint with DAG layout metadata and weakest-link identification.
- TRUST-8: Decay tick applied before returning graph.
- Architecture Section 12 & Section 14 (GET /cases/{id}/graph).
"""

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from groundtruth.api.auth import resolve_caller
from groundtruth.api.cases import get_db
from groundtruth.core.projector import load_case_projection
from groundtruth.core.replay import replay_case
from groundtruth.core.trust_service import apply_decay_tick
from groundtruth.core.utils import canonical_json

router = APIRouter(prefix="/cases", tags=["graph"])


class GraphNode(BaseModel):
    """Node in the causality graph representing an asserted fact."""

    fact_id: str
    type: str
    status: str
    own_trust: float
    effective_trust: float
    is_conclusion: bool
    verifier_state: str
    summary: str
    entity_key: str | None = None
    created_at: str


class GraphEdge(BaseModel):
    """Directed dependency edge from parent to child fact in the DAG."""

    from_fact_id: str = Field(description="Parent fact ID")
    to_fact_id: str = Field(description="Child fact ID")
    is_weakest_link: bool = Field(
        default=False,
        description="True if this incoming edge determines the child's effective trust",
    )


class GraphResponse(BaseModel):
    """Complete causality DAG for a case."""

    case_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


def extract_fact_summary(f_val: Any, f_type: str) -> str:
    """Produce human-readable 1-line summary for graph card."""
    if isinstance(f_val, dict):
        for k in ("message", "root_cause", "summary", "status", "advisory_id", "error", "sha"):
            if k in f_val and f_val[k]:
                return str(f_val[k])[:100]
    raw = canonical_json(f_val) if isinstance(f_val, dict | list) else str(f_val)
    return raw[:100]


@router.get("/{case_id}/graph", response_model=GraphResponse)
def get_case_graph(
    case_id: str,
    request: Request,
    at: int | None = Query(default=None, ge=1),
    authorization: str | None = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> GraphResponse:
    """Return nodes and edges with trust and weakest-link flags for DAG visualization (FR-7)."""
    if authorization:
        resolve_caller(
            conn=conn,
            authorization=authorization,
            target_case_id=case_id,
            endpoint_path=request.url.path,
        )

    if at is not None:
        state = replay_case(conn, case_id, upto_seq=at)
    else:
        # TRUST-8: Apply decay tick before /graph
        apply_decay_tick(conn=conn, case_id=case_id)
        state = load_case_projection(conn, case_id)

    if not state.case and not state.facts:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM events WHERE case_id = ? LIMIT 1", (case_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")

    nodes: list[GraphNode] = []
    for fid, f in state.facts.items():
        summary = extract_fact_summary(f.value, f.type)
        nodes.append(
            GraphNode(
                fact_id=fid,
                type=f.type,
                status=f.status,
                own_trust=f.own_trust,
                effective_trust=f.effective_trust,
                is_conclusion=bool(f.is_conclusion),
                verifier_state=f.verifier_state,
                summary=summary,
                entity_key=f.entity_key,
                created_at=f.created_at,
            )
        )

    edges: list[GraphEdge] = []
    for fid, child in state.facts.items():
        if not child.derived_from:
            continue

        # Find weakest parent edge that bottlenecks child effective trust
        parents_in_state = [p for p in child.derived_from if p in state.facts]
        if not parents_in_state:
            continue

        min_parent_eff = min(state.facts[p].effective_trust for p in parents_in_state)
        child_bottlenecked_by_parent = abs(child.effective_trust - min_parent_eff) < 1e-4

        for pid in parents_in_state:
            p_fact = state.facts[pid]
            is_weakest = child_bottlenecked_by_parent and (
                abs(p_fact.effective_trust - min_parent_eff) < 1e-4
            )
            edges.append(
                GraphEdge(
                    from_fact_id=pid,
                    to_fact_id=fid,
                    is_weakest_link=is_weakest,
                )
            )

    return GraphResponse(
        case_id=case_id,
        nodes=nodes,
        edges=edges,
    )
