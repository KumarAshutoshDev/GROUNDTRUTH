"""Authentication, token resolution, and case-scoped access enforcement.

Enforces:
- SEC-1: Tokens stored hashed; raw tokens returned once at issue.
- SEC-2: Tokens are case-scoped and expire when case is CLOSED.
- SEC-3: Reserved role restrictions (human role for override).
- SEC-5: Access denials logged to token's own case ledger or access_log table.
- INV-5: Identity derived from token, ignoring request body payloads.
- INV-10: Isolation between cases and out-of-contract actions.
"""

import hashlib
import os
import secrets
import sqlite3
from dataclasses import dataclass

from fastapi import HTTPException

from groundtruth.core.enums import EventType
from groundtruth.core.ledger import log_access
from groundtruth.core.pack import RESERVED_ROLES, DomainPack
from groundtruth.core.projector import append_and_project


@dataclass(frozen=True)
class AuthenticatedCaller:
    """Authenticated caller resolved exclusively from Bearer token."""

    agent_id: str
    role: str
    case_id: str
    token_hash: str


def hash_token(raw_token: str) -> str:
    """Compute SHA-256 hash of raw token."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def verify_bootstrap_key(provided_key: str | None) -> None:
    """Verify environment bootstrap key for opening new cases (SEC-4)."""
    expected_key = os.environ.get("GT_BOOTSTRAP_KEY", "gt-dev-bootstrap-secret-2026")
    if not provided_key or provided_key.strip() != expected_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing bootstrap key (X-Bootstrap-Key)",
        )


def issue_case_tokens(conn: sqlite3.Connection, case_id: str, pack: DomainPack) -> dict[str, str]:
    """Issue case-scoped tokens for all roles in the pack plus reserved roles (SEC-1, SEC-7)."""
    cursor = conn.cursor()
    issued: dict[str, str] = {}

    # Collect all roles: pack roles + reserved roles
    all_roles = list(pack.contracts.keys()) + list(RESERVED_ROLES.keys())

    for role in all_roles:
        secret_part = secrets.token_urlsafe(24)
        raw_token = f"gt_{role}_{secret_part}"
        t_hash = hash_token(raw_token)
        agent_id = f"{role}_{case_id[-6:]}" if not role.startswith("agent") else role

        cursor.execute(
            """
            INSERT INTO agent_tokens (token_hash, agent_id, role, case_id)
            VALUES (?, ?, ?, ?)
            """,
            (t_hash, agent_id, role, case_id),
        )
        issued[role] = raw_token

    return issued


def resolve_caller(
    conn: sqlite3.Connection,
    target_case_id: str,
    endpoint_path: str,
    authorization: str | None,
) -> AuthenticatedCaller:
    """Authenticate Bearer token and enforce case isolation (INV-5, INV-10, SEC-5)."""
    if not authorization or not authorization.startswith("Bearer "):
        log_access(
            conn=conn,
            caller=None,
            target_case_id=target_case_id,
            endpoint=endpoint_path,
            reason="missing_authorization_header",
        )
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    raw_token = authorization.removeprefix("Bearer ").strip()
    t_hash = hash_token(raw_token)

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT agent_id, role, case_id FROM agent_tokens
        WHERE token_hash = ?
        """,
        (t_hash,),
    )
    row = cursor.fetchone()

    if not row:
        log_access(
            conn=conn,
            caller=t_hash,
            target_case_id=target_case_id,
            endpoint=endpoint_path,
            reason="unknown_token",
        )
        raise HTTPException(status_code=401, detail="Unknown or invalid token")

    token_agent_id = row["agent_id"]
    token_role = row["role"]
    token_case_id = row["case_id"]

    # Check if target case exists
    cursor.execute("SELECT state FROM cases WHERE case_id = ?", (target_case_id,))
    target_case_row = cursor.fetchone()
    if not target_case_row:
        log_access(
            conn=conn,
            caller=t_hash,
            target_case_id=target_case_id,
            endpoint=endpoint_path,
            reason="unknown_case",
        )
        raise HTTPException(status_code=404, detail="Target case not found")

    # Check if token's case or target case is CLOSED (SEC-2)
    cursor.execute("SELECT state FROM cases WHERE case_id = ?", (token_case_id,))
    token_case_row = cursor.fetchone()
    if token_case_row and token_case_row["state"] == "CLOSED":
        log_access(
            conn=conn,
            caller=t_hash,
            target_case_id=token_case_id,
            endpoint=endpoint_path,
            reason="token_case_closed",
        )
        raise HTTPException(status_code=403, detail="Case is CLOSED; token has expired (SEC-2)")

    if target_case_row["state"] == "CLOSED":
        log_access(
            conn=conn,
            caller=t_hash,
            target_case_id=target_case_id,
            endpoint=endpoint_path,
            reason="target_case_closed",
        )
        raise HTTPException(status_code=403, detail="Target case is CLOSED; writes forbidden")

    # Enforce case isolation: token must match target case (INV-10)
    if token_case_id != target_case_id:
        # Cross-case attempt: append ACCESS_DENIED to the token's OWN case ledger (SEC-5)
        append_and_project(
            conn=conn,
            case_id=token_case_id,
            event_type=EventType.ACCESS_DENIED,
            actor=token_agent_id,
            payload={
                "attempted_case_id": target_case_id,
                "endpoint": endpoint_path,
                "role": token_role,
                "reason": "cross_case_access_denied",
            },
        )
        raise HTTPException(
            status_code=403,
            detail=f"Token is scoped to case {token_case_id}, cannot access case {target_case_id}",
        )

    return AuthenticatedCaller(
        agent_id=token_agent_id,
        role=token_role,
        case_id=token_case_id,
        token_hash=t_hash,
    )
