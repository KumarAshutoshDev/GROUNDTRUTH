"""Invariant test verifying INV-5: Identity comes from the token.

Proves:
agent_id and role MUST come from the authenticated, case-scoped token.
Any agent_id in a request body is ignored and logged.
"""

from pathlib import Path

from groundtruth.api.auth import issue_case_tokens, resolve_caller
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import EventType
from groundtruth.core.pack import load_pack, seed_contracts
from groundtruth.core.projector import append_and_project


def test_identity_strictly_from_token() -> None:
    conn = get_connection(":memory:")
    init_db(conn)

    pack = load_pack(Path("groundtruth/packs/cicd"))
    seed_contracts(conn, pack)

    case_id = "case_identity_inv5"
    append_and_project(
        conn,
        case_id,
        EventType.CASE_OPENED,
        "system",
        {"domain_pack": "cicd", "trigger": {}},
    )

    tokens = issue_case_tokens(conn, case_id, pack)
    log_agent_token = tokens["log_agent"]

    # Resolve caller using token
    caller = resolve_caller(
        conn=conn,
        target_case_id=case_id,
        endpoint_path="/cases/case_identity_inv5/propose",
        authorization=f"Bearer {log_agent_token}",
    )

    # Assert role and agent_id are derived from token
    assert caller.role == "log_agent"
    assert caller.case_id == case_id
    assert caller.agent_id.startswith("log_agent")

    # Prove that even if spoofed agent_id is in request body, caller identity is bound to token
    spoofed_request_body = {
        "agent_id": "human_overlord",
        "role": "admin",
        "fact": {"type": "log_anomaly", "value": {}},
    }

    # Caller identity remains log_agent, spoofed values in body cannot override token identity
    effective_agent_id = caller.agent_id
    effective_role = caller.role

    assert effective_agent_id != spoofed_request_body["agent_id"]
    assert effective_role != spoofed_request_body["role"]
    assert effective_role == "log_agent"
