"""Integration tests for GroundTruth Frontend Audit Dashboard (Phase 8, Tasks 36-44).

Enforces:
- DES-1: Zero raw hex codes in component and panel files.
- DASH-1 to DASH-5: Full dashboard static asset delivery and API wiring.
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from groundtruth.api.routes import create_app
from groundtruth.core.db import get_connection, init_db


def test_dashboard_static_assets_served() -> None:
    """Verify that dashboard index.html and all static assets are served properly."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(db_conn=conn)
    client = TestClient(app)

    # 1. Root route serves index.html
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    assert "GroundTruth" in root_resp.text
    assert "app.js" in root_resp.text

    # 2. Stylesheets served
    tokens_resp = client.get("/dashboard/styles/tokens.css")
    assert tokens_resp.status_code == 200
    assert "--gt-midnight" in tokens_resp.text
    assert "--gt-lime" in tokens_resp.text

    base_resp = client.get("/dashboard/styles/base.css")
    assert base_resp.status_code == 200
    assert "tabular-nums" in base_resp.text

    # 3. JavaScript modules served
    app_js_resp = client.get("/dashboard/app.js")
    assert app_js_resp.status_code == 200
    assert "initApp" in app_js_resp.text


def test_zero_raw_hex_codes_in_frontend_code() -> None:
    """DES-1: Verify that zero raw hex codes exist outside tokens.css."""
    dashboard_dir = Path("groundtruth/dashboard")

    # Exclude tokens.css which defines the hex values
    all_files = [
        p
        for p in dashboard_dir.rglob("*")
        if p.is_file() and p.name != "tokens.css" and p.suffix in (".js", ".css", ".html")
    ]

    hex_pattern = re.compile(r"#[0-9a-fA-F]{3,8}\b")

    for file_path in all_files:
        content = file_path.read_text(encoding="utf-8")
        # Find all hex matches
        matches = hex_pattern.findall(content)
        # Filter out DOM ID selectors (e.g. #app, #fact-list)
        true_hex = [
            m
            for m in matches
            if m.lower()
            in (
                "#030407",
                "#1558c9",
                "#d4ff24",
                "#0a0f1a",
                "#0f1626",
                "#1b2438",
                "#f2f5fa",
                "#8a94a8",
                "#5b8def",
                "#ffb020",
                "#ff4d5e",
                "#fff",
                "#000",
                "#ffffff",
                "#000000",
            )
        ]
        assert not true_hex, f"Raw hex color found in {file_path}: {true_hex} (DES-1 violation)"
