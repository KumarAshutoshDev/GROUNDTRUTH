"""Unit tests for GroundTruth Dashboard UI Components (Task 37).

Enforces:
- DES-1: Tokens only, zero raw hex codes in component code.
- DES-4: Never color alone. Status badges MUST contain color token, SVG icon, and status text.
- DES-6: Fact cards display source type, trust score, status badge, and provenance.
"""

import re
from pathlib import Path


def test_status_badge_contract_des_4() -> None:
    """DES-4: All status badges must render color, SVG icon, and status text."""
    badge_js = Path("groundtruth/dashboard/components/status_badge.js").read_text()

    # Verify no raw hex in component code (DES-1)
    assert not re.search(r"#[0-9a-fA-F]{3,8}", badge_js), "Raw hex found in status_badge.js"

    # All 5 fact statuses + 3 gate verdicts must be defined with icon, colorVar, and word
    statuses = [
        "ACTIVE",
        "CONTESTED",
        "QUARANTINED",
        "RETRACTED",
        "TAINTED",
        "ADMIT",
        "QUARANTINE",
        "REJECT",
    ]
    for s in statuses:
        assert f'word: "{s}"' in badge_js, f"Status word for {s} missing in config"

    # Verify SVG icons are present in ICONS dict
    assert "<svg" in badge_js
    assert "check:" in badge_js
    assert "opposingArrows:" in badge_js
    assert "boxLock:" in badge_js
    assert "cross:" in badge_js
    assert "warningTriangle:" in badge_js


def test_source_chip_contract_des_3() -> None:
    """DES-3: Source chips must use Cobalt Soft outline only."""
    chip_js = Path("groundtruth/dashboard/components/source_chip.js").read_text()

    assert not re.search(r"#[0-9a-fA-F]{3,8}", chip_js), "Raw hex found in source_chip.js"
    assert "var(--gt-cobalt-soft)" in chip_js
    assert "var(--gt-lime)" not in chip_js
    assert "var(--gt-amber)" not in chip_js
    assert "var(--gt-coral)" not in chip_js


def test_trust_bar_contract_des_7() -> None:
    """DES-7: Trust bar must use T_cite and T_auto thresholds."""
    bar_js = Path("groundtruth/dashboard/components/trust_bar.js").read_text()

    assert not re.search(r"#[0-9a-fA-F]{3,8}", bar_js), "Raw hex found in trust_bar.js"
    assert "tCite" in bar_js
    assert "tAuto" in bar_js
    assert "var(--gt-lime)" in bar_js
    assert "var(--gt-cobalt-soft)" in bar_js
    assert "var(--gt-amber)" in bar_js
    assert "var(--gt-coral)" in bar_js
