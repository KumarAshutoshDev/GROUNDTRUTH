"""Invariant test verifying TRUST-7, CASE-5, and SEC-7 pack validation."""

import json
from pathlib import Path

import pytest
import yaml

from groundtruth.core.db import get_connection, init_db
from groundtruth.core.pack import PackValidationError, load_pack, seed_contracts


@pytest.fixture
def valid_pack_dir(tmp_path: Path) -> Path:
    pack = tmp_path / "valid_pack"
    pack.mkdir()

    schema = {
        "fact_types": {
            "log_anomaly": {"description": "A detected anomaly in logs"},
            "cicd_root_cause": {"description": "Diagnosis conclusion"},
        }
    }
    (pack / "schema.json").write_text(json.dumps(schema), encoding="utf-8")

    trust = {
        "BASE": {
            "human_input": 0.95,
            "tool_output": 0.90,
            "document": 0.70,
            "agent_inference": 0.60,
        },
        "DOWNGRADE_CAP": 0.30,
        "T_cite": 0.50,
        "T_auto": 0.60,
        "decay_epsilon": 0.01,
        "half_lives": {"log_anomaly": 21600},
        "budget": {"max_tool_calls": 20, "max_tokens": 100000},
    }
    (pack / "trust.yaml").write_text(yaml.dump(trust), encoding="utf-8")

    contracts = {
        "conclusion_type": "cicd_root_cause",
        "roles": {
            "diagnoser": {
                "reads": ["log_anomaly"],
                "writes": ["cicd_root_cause"],
                "max_context_tokens": 4000,
                "min_trust_threshold": 0.50,
            }
        },
    }
    (pack / "contracts.yaml").write_text(yaml.dump(contracts), encoding="utf-8")

    return pack


def test_valid_pack_loading(valid_pack_dir: Path) -> None:
    pack = load_pack(valid_pack_dir)
    assert pack.name == "valid_pack"
    assert pack.conclusion_type == "cicd_root_cause"
    assert "diagnoser" in pack.contracts

    conn = get_connection(":memory:")
    init_db(conn)
    seed_contracts(conn, pack)

    # Check contracts table
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM contracts")
    roles = {row[0] for row in cursor.fetchall()}
    assert "diagnoser" in roles
    assert "orchestrator" in roles
    assert "human" in roles


def test_trust_7_t_auto_exceeds_base(valid_pack_dir: Path) -> None:
    trust_file = valid_pack_dir / "trust.yaml"
    trust = yaml.safe_load(trust_file.read_text(encoding="utf-8"))
    trust["T_auto"] = 0.65  # Exceeds BASE[agent_inference] (0.60)
    trust_file.write_text(yaml.dump(trust), encoding="utf-8")

    with pytest.raises(PackValidationError, match="TRUST-7 violation"):
        load_pack(valid_pack_dir)


def test_trust_7_t_cite_not_less_than_t_auto(valid_pack_dir: Path) -> None:
    trust_file = valid_pack_dir / "trust.yaml"
    trust = yaml.safe_load(trust_file.read_text(encoding="utf-8"))
    trust["T_cite"] = 0.60  # Not strictly < T_auto (0.60)
    trust_file.write_text(yaml.dump(trust), encoding="utf-8")

    with pytest.raises(PackValidationError, match="TRUST-7 violation"):
        load_pack(valid_pack_dir)


def test_case_5_conclusion_type_not_in_schema(valid_pack_dir: Path) -> None:
    contracts_file = valid_pack_dir / "contracts.yaml"
    contracts = yaml.safe_load(contracts_file.read_text(encoding="utf-8"))
    contracts["conclusion_type"] = "unknown_type"
    contracts_file.write_text(yaml.dump(contracts), encoding="utf-8")

    with pytest.raises(
        PackValidationError,
        match="CASE-5 violation: conclusion_type 'unknown_type' not declared in schema.json",
    ):
        load_pack(valid_pack_dir)


def test_case_5_conclusion_type_not_writable(valid_pack_dir: Path) -> None:
    contracts_file = valid_pack_dir / "contracts.yaml"
    contracts = yaml.safe_load(contracts_file.read_text(encoding="utf-8"))
    contracts["roles"]["diagnoser"]["writes"] = ["other_fact"]
    contracts_file.write_text(yaml.dump(contracts), encoding="utf-8")

    with pytest.raises(
        PackValidationError,
        match="CASE-5 violation: conclusion_type 'cicd_root_cause' is not in writes of any role",
    ):
        load_pack(valid_pack_dir)


def test_sec_7_cannot_redefine_reserved_role(valid_pack_dir: Path) -> None:
    contracts_file = valid_pack_dir / "contracts.yaml"
    contracts = yaml.safe_load(contracts_file.read_text(encoding="utf-8"))
    contracts["roles"]["human"] = {
        "reads": ["*"],
        "writes": ["cicd_root_cause"],
        "max_context_tokens": 1000,
        "min_trust_threshold": 0.0,
    }
    contracts_file.write_text(yaml.dump(contracts), encoding="utf-8")

    with pytest.raises(PackValidationError, match="SEC-7 violation"):
        load_pack(valid_pack_dir)
