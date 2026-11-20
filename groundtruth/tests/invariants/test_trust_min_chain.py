"""Invariant Test: test_trust_min_chain.

Enforces:
- INV-8: Trust only goes down the chain.
  effective_trust = min(own_trust, min(parents' effective_trust)).
  No code may raise a child above its weakest parent.
- TRUST-1: Self-confidence capping and downgrade capping.
- TRUST-6: Tainted or retracted facts have own_trust = 0.0, collapsing downstream.
- INV-6: trust.py imports no LLM adapters or provider SDKs.
"""

import ast
import inspect
from datetime import UTC, datetime
from pathlib import Path

import groundtruth.core.trust as trust_module
from groundtruth.core.enums import FactStatus, SourceType, VerifierState
from groundtruth.core.models import FactModel
from groundtruth.core.pack import load_pack
from groundtruth.core.trust import effective_trust, own_trust


def test_trust_module_has_no_llm_imports() -> None:
    """Enforce INV-6: trust.py must never import adapters/ or provider SDKs."""
    source_file = inspect.getfile(trust_module)
    with open(source_file, encoding="utf-8") as f:
        tree = ast.parse(f.read())

    forbidden_prefixes = ("groundtruth.adapters", "openai", "anthropic", "google.generativeai")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for forbidden in forbidden_prefixes:
                    assert not alias.name.startswith(forbidden), (
                        f"Forbidden import '{alias.name}' in trust.py"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for forbidden in forbidden_prefixes:
                    assert not node.module.startswith(forbidden), (
                        f"Forbidden from-import '{node.module}' in trust.py"
                    )


def test_trust_min_chain_and_transitive_capping() -> None:
    """Enforce INV-8: Child effective trust never exceeds the weakest link in its ancestry."""
    pack = load_pack(Path("groundtruth/packs/cicd"))
    now = datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC)

    # 1. Parent A: Tool output (base 0.90)
    fact_a = FactModel(
        fact_id="fact_a",
        case_id="case_1",
        type="log_anomaly",
        value={"msg": "error"},
        source="log_agent",
        source_type=SourceType.TOOL_OUTPUT.value,
        agent_id="log_agent",
        created_at="2026-11-19T11:59:00Z",
        self_confidence=1.0,
        own_trust=0.90,
        effective_trust=0.90,
        status=FactStatus.ACTIVE.value,
    )

    # 2. Parent B: Document (base 0.70)
    fact_b = FactModel(
        fact_id="fact_b",
        case_id="case_1",
        type="intel_match",
        value={"adv": "CVE-01"},
        source="intel_agent",
        source_type=SourceType.DOCUMENT.value,
        agent_id="intel_agent",
        created_at="2026-11-19T11:59:00Z",
        self_confidence=1.0,
        own_trust=0.70,
        effective_trust=0.70,
        status=FactStatus.ACTIVE.value,
    )

    # 3. Child C: Agent Inference (base 0.60) deriving from A and B
    fact_c = FactModel(
        fact_id="fact_c",
        case_id="case_1",
        type="cicd_root_cause",
        value={"cause": "bug"},
        source="repo_agent",
        source_type=SourceType.AGENT_INFERENCE.value,
        agent_id="repo_agent",
        created_at="2026-11-19T11:59:30Z",
        self_confidence=0.95,
        own_trust=0.60,
        effective_trust=0.60,
        status=FactStatus.ACTIVE.value,
        derived_from=["fact_a", "fact_b"],
    )

    facts = {"fact_a": fact_a, "fact_b": fact_b, "fact_c": fact_c}

    # Under normal conditions, min(own_trust(C)=0.60, eff(A)=0.90, eff(B)=0.70) == 0.60
    assert effective_trust(fact_c, facts, pack, now) == 0.60

    # 4. Weak parent test: Downgrade parent B below 0.60 (e.g. to 0.30 via DOWNGRADE_CAP)
    fact_b.verifier_state = VerifierState.DOWNGRADED.value
    assert own_trust(fact_b, pack, now) == 0.30
    # Child C must collapse to 0.30! Child CANNOT exceed its weakest parent (INV-8)
    assert effective_trust(fact_c, facts, pack, now) == 0.30

    # 5. Taint test (TRUST-6): If parent A becomes TAINTED, its own_trust becomes 0.0
    fact_b.verifier_state = VerifierState.SUPPORTED.value  # Restore B
    fact_a.status = FactStatus.TAINTED.value
    assert own_trust(fact_a, pack, now) == 0.0
    # Child C must collapse to 0.0!
    assert effective_trust(fact_c, facts, pack, now) == 0.0


def test_multi_hop_transitive_trust_propagation() -> None:
    """Enforce INV-8 across a 4-hop chain: Root -> Mid1 -> Mid2 -> Leaf."""
    pack = load_pack(Path("groundtruth/packs/cicd"))
    now = datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC)

    root = FactModel(
        fact_id="f_root",
        case_id="case_1",
        type="log_anomaly",
        value={"msg": "root log"},
        source="log_agent",
        source_type=SourceType.TOOL_OUTPUT.value,
        agent_id="log_agent",
        created_at="2026-11-19T12:00:00Z",
        self_confidence=1.0,
        own_trust=0.90,
        effective_trust=0.90,
        status=FactStatus.ACTIVE.value,
    )

    mid1 = FactModel(
        fact_id="f_mid1",
        case_id="case_1",
        type="commit_change",
        value={"sha": "123"},
        source="repo_agent",
        source_type=SourceType.TOOL_OUTPUT.value,
        agent_id="repo_agent",
        created_at="2026-11-19T11:56:00Z",
        self_confidence=1.0,
        own_trust=0.90,
        effective_trust=0.90,
        status=FactStatus.ACTIVE.value,
        derived_from=["f_root"],
    )

    mid2 = FactModel(
        fact_id="f_mid2",
        case_id="case_1",
        type="agent_inference",
        value={"sub": "mid conclusion"},
        source="repo_agent",
        source_type=SourceType.AGENT_INFERENCE.value,
        agent_id="repo_agent",
        created_at="2026-11-19T11:57:00Z",
        self_confidence=0.80,
        own_trust=0.60,
        effective_trust=0.60,
        status=FactStatus.ACTIVE.value,
        derived_from=["f_mid1"],
    )

    leaf = FactModel(
        fact_id="f_leaf",
        case_id="case_1",
        type="cicd_root_cause",
        value={"root_cause": "deep defect"},
        source="repo_agent",
        source_type=SourceType.AGENT_INFERENCE.value,
        agent_id="repo_agent",
        created_at="2026-11-19T11:58:00Z",
        self_confidence=1.0,
        own_trust=0.60,
        effective_trust=0.60,
        status=FactStatus.ACTIVE.value,
        derived_from=["f_mid2"],
    )

    facts = {"f_root": root, "f_mid1": mid1, "f_mid2": mid2, "f_leaf": leaf}

    # Initial chain effective trust: min(0.60, 0.60, 0.90, 0.90) == 0.60
    assert effective_trust(leaf, facts, pack, now) == 0.60

    # If the root fact is downgraded to 0.30, leaf must drop to 0.30
    root.verifier_state = VerifierState.DOWNGRADED.value
    assert effective_trust(leaf, facts, pack, now) == 0.30
