"""API integration tests for Server-Sent Events (SSE) Stream endpoint (Task 34).

Enforces:
- GET /cases/{id}/stream streams existing events on connect and live events as appended.
- Events formatted as standard SSE packets (event, data, id).
- Verification: Async test connecting SSE client, triggering a verdict,
  and receiving streaming event packet within 500ms.
"""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from groundtruth.adapters.llm import MockFixtureLLMAdapter
from groundtruth.api.propose import get_verifier_adapter
from groundtruth.api.routes import create_app
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import EventType, GateVerdict, SourceType
from groundtruth.core.projector import append_and_project


def test_stream_replay_past_events() -> None:
    """Test that past events replay on connect."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(db_conn=conn)
    client = TestClient(app)

    # Open case
    resp = client.post(
        "/cases",
        json={"domain_pack": "cicd", "trigger": {"service": "stream-test"}},
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
    )
    assert resp.status_code == 200
    case_id = resp.json()["case_id"]

    # Append an event
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="log_agent",
        payload={
            "fact": {
                "fact_id": "f_stream_1",
                "type": "log_anomaly",
                "source": "log_agent",
                "source_type": SourceType.TOOL_OUTPUT.value,
            },
            "verdict": GateVerdict.ADMIT.value,
        },
    )

    # Check that past events are present in stream response text
    response = client.get(f"/cases/{case_id}/stream?max_events=2")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: CASE_OPENED" in response.text
    assert "event: GATE_VERDICT" in response.text
    assert "f_stream_1" in response.text


@pytest.mark.anyio
async def test_stream_live_events_reception() -> None:
    """Async test asserting that a live verdict event is streamed and received within 500ms."""
    conn = get_connection(":memory:")
    init_db(conn)
    adapter = MockFixtureLLMAdapter()
    app = create_app(db_conn=conn)
    app.dependency_overrides[get_verifier_adapter] = lambda: adapter

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Open case using async client
        resp = await client.post(
            "/cases",
            json={"domain_pack": "cicd", "trigger": {"service": "live-stream"}},
            headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        )
        assert resp.status_code == 200
        case_id = resp.json()["case_id"]

        # Background task: propose fact after 50ms
        async def trigger_live_verdict() -> None:
            await asyncio.sleep(0.05)
            append_and_project(
                conn=conn,
                case_id=case_id,
                event_type=EventType.GATE_VERDICT,
                actor="log_agent",
                payload={
                    "fact": {
                        "fact_id": "fact_live_sse_99",
                        "type": "log_anomaly",
                        "value": {"error": "live exception"},
                        "source": "log_agent",
                        "source_type": SourceType.TOOL_OUTPUT.value,
                        "agent_id": "log_agent",
                    },
                    "verdict": GateVerdict.ADMIT.value,
                    "own_trust": 0.9,
                    "effective_trust": 0.9,
                },
            )

        start_time = asyncio.get_running_loop().time()
        task = asyncio.create_task(trigger_live_verdict())

        # Connect to stream for live event
        live_resp = await client.get(f"/cases/{case_id}/stream?since_seq=1&max_events=1")
        await task
        elapsed = asyncio.get_running_loop().time() - start_time

        assert live_resp.status_code == 200
        assert "fact_live_sse_99" in live_resp.text
        assert "GATE_VERDICT" in live_resp.text
        assert elapsed < 0.5  # Received within 500ms
