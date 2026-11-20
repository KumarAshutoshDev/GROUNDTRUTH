"""Unit tests for GroundTruth evaluation runner and comparative report (Task 46).

Enforces: CLAIM-1, CLAIM-2, CLAIM-3.
"""

import json

from groundtruth.eval.gt_run import OUTPUT_PATH as GT_OUTPUT_PATH
from groundtruth.eval.gt_run import run_all_gt
from groundtruth.eval.report import REPORT_PATH, generate_report


def test_gt_eval_execution() -> None:
    """Test GroundTruth evaluation runner executes across fixtures (N=15) and persists metrics."""
    gt_summary = run_all_gt(runs_per_fixture=3)

    assert gt_summary["sample_size"] == 15
    assert len(gt_summary["runs"]) == 15
    assert "aggregates" in gt_summary
    agg = gt_summary["aggregates"]

    assert agg["mean_tool_calls"] > 0
    assert agg["stdev_tool_calls"] > 0.0
    assert agg["mean_total_tokens"] > 0
    assert agg["stdev_total_tokens"] > 0.0
    assert agg["mean_accuracy"] == 1.0
    assert agg["total_blocked_writes"] == 15

    assert len(gt_summary["fixtures"]) == 5
    for _fid, res in gt_summary["fixtures"].items():
        assert res["accuracy"] == 1.0
        assert res["tool_calls"] > 0
        assert res["total_tokens"] > 0
        assert "fixture_clock_used" in res

    assert GT_OUTPUT_PATH.exists()
    with open(GT_OUTPUT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert data["sample_size"] == 15


def test_comparative_report_generation() -> None:
    """Test comparative report generation enforcing CLAIM-1, CLAIM-2, CLAIM-3."""
    report_md = generate_report()

    assert REPORT_PATH.exists()
    assert len(report_md) > 500

    # Enforce CLAIM-1: No forbidden superlatives
    forbidden_words = ["novel", "first ever", "nobody does this", "unique"]
    report_lower = report_md.lower()
    for word in forbidden_words:
        assert word not in report_lower, f"Forbidden word '{word}' found in report (CLAIM-1)"

    # Enforce CLAIM-1 required phrasing
    assert "we apply and compose established ideas and measure the result" in report_lower

    # Enforce CLAIM-3: Sample size and baseline definition
    assert "sample size" in report_lower
    assert "baseline definition" in report_lower
    assert "n = 15" in report_lower

    # Target reductions met
    assert "≥ 40%" in report_md
    assert "≥ 35%" in report_md
    assert "✅" in report_md
    assert "cost / successful diagnosis" in report_lower
