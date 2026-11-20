"""Domain Pack loader, validation, and contract seeding.

Enforces:
- TRUST-7: Pack loader MUST reject a pack unless T_cite < T_auto <= BASE[agent_inference].
- CASE-5: conclusion_type must exist in schema.json and in writes of at least one contract.
- TRUST-2: Thresholds, decay, and budgets come from pack config, not literals in code.
- SEC-7: Reserved roles (orchestrator, human) seeded automatically into contracts table.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from groundtruth.core.utils import canonical_json


class PackValidationError(Exception):
    """Raised when a domain pack fails validation."""

    pass


class BudgetConfig(BaseModel):
    max_tool_calls: int = Field(gt=0)
    max_tokens: int = Field(gt=0)


class TrustConfig(BaseModel):
    BASE: dict[str, float]
    DOWNGRADE_CAP: float = Field(ge=0.0, le=1.0)
    T_cite: float = Field(ge=0.0, le=1.0)
    T_auto: float = Field(ge=0.0, le=1.0)
    decay_epsilon: float = Field(default=0.01, ge=0.0)
    half_lives: dict[str, float | None] = Field(default_factory=dict)
    budget: BudgetConfig


class RoleContract(BaseModel):
    role: str
    reads: list[str]
    writes: list[str]
    max_context_tokens: int = Field(ge=0)
    min_trust_threshold: float = Field(ge=0.0, le=1.0)


class DomainPack(BaseModel):
    name: str
    conclusion_type: str
    schema_def: dict[str, Any]
    trust: TrustConfig
    contracts: dict[str, RoleContract]
    checks: dict[str, Any] = Field(default_factory=dict)
    path: Path


RESERVED_ROLES: dict[str, RoleContract] = {
    "orchestrator": RoleContract(
        role="orchestrator",
        reads=[],
        writes=[],
        max_context_tokens=0,
        min_trust_threshold=0.0,
    ),
    "human": RoleContract(
        role="human",
        reads=["*"],
        writes=[],
        max_context_tokens=0,
        min_trust_threshold=0.0,
    ),
}


def load_pack(pack_dir: Path | str) -> DomainPack:
    """Load, parse, and strictly validate a domain pack."""
    path = Path(pack_dir)
    if not path.is_dir():
        raise PackValidationError(f"Domain pack directory does not exist: {path}")

    schema_file = path / "schema.json"
    trust_file = path / "trust.yaml"
    contracts_file = path / "contracts.yaml"
    checks_file = path / "checks.yaml"

    if not schema_file.exists():
        raise PackValidationError(f"Missing schema.json in pack {path.name}")
    if not trust_file.exists():
        raise PackValidationError(f"Missing trust.yaml in pack {path.name}")
    if not contracts_file.exists():
        raise PackValidationError(f"Missing contracts.yaml in pack {path.name}")

    # 1. Parse schema.json
    try:
        schema_data = json.loads(schema_file.read_text(encoding="utf-8"))
    except Exception as e:
        raise PackValidationError(f"Failed to parse schema.json: {e}") from e

    # 2. Parse trust.yaml
    try:
        trust_raw = yaml.safe_load(trust_file.read_text(encoding="utf-8"))
        trust_config = TrustConfig(**trust_raw)
    except Exception as e:
        raise PackValidationError(f"Failed to parse trust.yaml: {e}") from e

    # 3. Parse contracts.yaml and conclusion_type
    try:
        contracts_raw = yaml.safe_load(contracts_file.read_text(encoding="utf-8"))
        conclusion_type = contracts_raw.get("conclusion_type")
        roles_raw = contracts_raw.get("roles", {})
        contracts_dict: dict[str, RoleContract] = {}
        for role_name, rdata in roles_raw.items():
            contracts_dict[role_name] = RoleContract(role=role_name, **rdata)
    except Exception as e:
        raise PackValidationError(f"Failed to parse contracts.yaml: {e}") from e

    # Parse optional checks.yaml
    checks_data: dict[str, Any] = {}
    if checks_file.exists():
        try:
            checks_data = yaml.safe_load(checks_file.read_text(encoding="utf-8")) or {}
        except Exception as e:
            raise PackValidationError(f"Failed to parse checks.yaml: {e}") from e

    # 4. Enforce TRUST-7: T_cite < T_auto <= BASE[agent_inference]
    inf_base = trust_config.BASE.get("agent_inference")
    if inf_base is None:
        raise PackValidationError("BASE missing 'agent_inference' in trust.yaml")

    if not (trust_config.T_cite < trust_config.T_auto <= inf_base):
        raise PackValidationError(
            f"TRUST-7 violation: Require T_cite ({trust_config.T_cite}) < "
            f"T_auto ({trust_config.T_auto}) <= BASE[agent_inference] ({inf_base})"
        )

    # 5. Enforce CASE-5: conclusion_type must exist in schema.json and in writes
    # of at least one role
    if not conclusion_type:
        raise PackValidationError("CASE-5 violation: conclusion_type missing in contracts.yaml")

    fact_types = schema_data.get("fact_types", {})
    if conclusion_type not in fact_types:
        raise PackValidationError(
            f"CASE-5 violation: conclusion_type '{conclusion_type}' not declared in schema.json"
        )

    writable_roles = [
        role for role, contract in contracts_dict.items() if conclusion_type in contract.writes
    ]
    if not writable_roles:
        raise PackValidationError(
            f"CASE-5 violation: conclusion_type '{conclusion_type}' is not in writes of any role"
        )

    # Enforce SEC-7: Domain packs must not redefine reserved roles
    for reserved in RESERVED_ROLES:
        if reserved in contracts_dict:
            raise PackValidationError(
                f"SEC-7 violation: Domain pack cannot redefine reserved role '{reserved}'"
            )

    return DomainPack(
        name=path.name,
        conclusion_type=conclusion_type,
        schema_def=schema_data,
        trust=trust_config,
        contracts=contracts_dict,
        checks=checks_data,
        path=path,
    )


def seed_contracts(conn: sqlite3.Connection, pack: DomainPack) -> None:
    """Seed the contracts table with domain pack roles and reserved roles (SEC-7)."""
    cursor = conn.cursor()

    # Seed pack roles
    for role_name, contract in pack.contracts.items():
        cursor.execute(
            """
            INSERT OR REPLACE INTO contracts (
                role, reads, writes, max_context_tokens, min_trust_threshold
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                role_name,
                canonical_json(contract.reads),
                canonical_json(contract.writes),
                contract.max_context_tokens,
                contract.min_trust_threshold,
            ),
        )

    # Seed reserved roles (SEC-7)
    for res_name, res_contract in RESERVED_ROLES.items():
        cursor.execute(
            """
            INSERT OR REPLACE INTO contracts (
                role, reads, writes, max_context_tokens, min_trust_threshold
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                res_name,
                canonical_json(res_contract.reads),
                canonical_json(res_contract.writes),
                res_contract.max_context_tokens,
                res_contract.min_trust_threshold,
            ),
        )
