"""Unit test for 4-minute demo script automation (Task 47)."""

from groundtruth.eval.demo_script import DemoRunner


def test_demo_script_execution() -> None:
    """Verify all 8 demo beats execute end-to-end and complete in under 4 minutes."""
    runner = DemoRunner(offline=True, delay_seconds=0.0)
    result = runner.execute_all_beats()

    assert result["status"] == "SUCCESS"
    assert result["beats_executed"] == 8
    assert result["elapsed_seconds"] < 240.0  # 4 minutes = 240 seconds
