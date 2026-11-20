"""Unit tests verifying the reference CI/CD domain pack and its fixtures."""

import json
from pathlib import Path

from groundtruth.core.pack import load_pack


def test_load_cicd_pack() -> None:
    pack_dir = Path("groundtruth/packs/cicd")
    pack = load_pack(pack_dir)

    assert pack.name == "cicd"
    assert pack.conclusion_type == "cicd_root_cause"
    assert set(pack.contracts.keys()) == {"log_agent", "repo_agent", "intel_agent"}

    # Verify trust config
    assert pack.trust.T_cite == 0.50
    assert pack.trust.T_auto == 0.60
    assert pack.trust.BASE["agent_inference"] == 0.60
    assert pack.trust.budget.max_tool_calls == 20
    assert pack.trust.budget.max_tokens == 100000

    # Verify 5 fixtures exist and have required ground truth fields
    fixtures_dir = pack_dir / "fixtures"
    fixture_files = sorted(fixtures_dir.glob("fixture_*.json"))
    assert len(fixture_files) == 5

    for fpath in fixture_files:
        data = json.loads(fpath.read_text(encoding="utf-8"))
        assert "fixture_id" in data
        assert "title" in data
        assert "build_log" in data
        assert "ground_truth_cause" in data
