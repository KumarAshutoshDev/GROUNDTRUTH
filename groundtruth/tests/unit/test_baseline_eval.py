"""Unit tests for baseline evaluation runner (Task 45, FIX-5, CLAIM-2, CLAIM-3)."""

import json
from pathlib import Path

from groundtruth.eval.baseline_run import OUTPUT_PATH, run_all_baselines


def test_baseline_eval_execution(tmp_path: Path) -> None:
    """Test that the baseline runner executes against fixtures and outputs expected metrics."""
    metrics = run_all_baselines(runs_per_fixture=3)

    assert metrics["sample_size"] == 15
    assert len(metrics["runs"]) == 15
    assert "aggregates" in metrics
    agg = metrics["aggregates"]
    assert agg["total_tool_calls"] > 0
    assert agg["mean_tool_calls"] > 0
    assert agg["stdev_tool_calls"] > 0.0
    assert agg["total_duplicate_calls"] > 0
    assert agg["stdev_duplicate_calls"] > 0.0
    assert agg["total_tokens"] > 0
    assert agg["stdev_total_tokens"] > 0.0

    assert len(metrics["fixtures"]) == 5
    for _fid, fmetrics in metrics["fixtures"].items():
        assert fmetrics["tool_calls"] > 0
        assert fmetrics["total_tokens"] > 0
        assert "duplicate_tool_calls" in fmetrics

    # Check file written
    assert OUTPUT_PATH.exists()
    with open(OUTPUT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert data["sample_size"] == 15
