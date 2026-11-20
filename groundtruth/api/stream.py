"""Real-Time Server-Sent Events (SSE) Stream Endpoint (Task 34, Architecture Section 12).

Provides live streaming of:
- GATE_VERDICT
- TRUST_RECOMPUTED
- FACT_TAINTED
- CONFLICT_RAISED
- ACCESS_DENIED
- All case ledger events formatted as canonical JSON with sequence number.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from groundtruth.api.auth import resolve_caller
from groundtruth.api.cases import get_db
from groundtruth.core.ledger import Event
from groundtruth.core.projector import (
    add_event_listener,
    load_case_projection,
    remove_event_listener,
)
from groundtruth.core.utils import canonical_json

router = APIRouter(prefix="/cases", tags=["stream"])


@router.get("/{case_id}/stream")
async def stream_case_events(
    case_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    since_seq: int = Query(default=0),
    max_events: int | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> StreamingResponse:
    """Stream live Server-Sent Events for a case."""
    # Authenticate if token provided (supports Authorization header or query param)
    auth_header = authorization or (f"Bearer {token}" if token else None)
    if auth_header:
        resolve_caller(
            conn=conn,
            target_case_id=case_id,
            endpoint_path=request.url.path,
            authorization=auth_header,
        )

    # Verify case exists
    state = load_case_projection(conn, case_id)
    if not state.case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Determine starting sequence number for replay
    start_seq = since_seq
    if last_event_id:
        try:
            start_seq = max(start_seq, int(last_event_id))
        except ValueError:
            pass

    # Fetch past events for replay
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT event_id, case_id, seq, event_type, actor, payload, ts, prev_hash, hash
        FROM events
        WHERE case_id = ? AND seq > ?
        ORDER BY seq ASC
        """,
        (case_id, start_seq),
    )
    past_events: list[dict[str, Any]] = [dict(row) for row in cursor.fetchall()]

    event_queue: asyncio.Queue[Event] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_new_event(evt: Event) -> None:
        if evt.case_id == case_id:
            try:
                loop.call_soon_threadsafe(event_queue.put_nowait, evt)
            except Exception:
                pass

    add_event_listener(on_new_event)

    async def event_generator() -> AsyncGenerator[str, None]:
        yielded_count = 0
        try:
            # 1. Yield past events
            for p_evt in past_events:
                p_payload = p_evt["payload"]
                if isinstance(p_payload, str):
                    try:
                        p_payload = json.loads(p_payload)
                    except Exception:
                        pass
                p_data = {
                    "event_id": p_evt["event_id"],
                    "case_id": p_evt["case_id"],
                    "seq": p_evt["seq"],
                    "event_type": p_evt["event_type"],
                    "actor": p_evt["actor"],
                    "payload": p_payload,
                    "ts": p_evt["ts"],
                    "prev_hash": p_evt["prev_hash"],
                    "hash": p_evt["hash"],
                }
                yield (
                    f"id: {p_evt['seq']}\n"
                    f"event: {p_evt['event_type']}\n"
                    f"data: {canonical_json(p_data)}\n\n"
                )
                yielded_count += 1
                if max_events is not None and yielded_count >= max_events:
                    return

            # 2. Yield live events as they arrive
            while True:
                live_evt = await event_queue.get()
                live_data = {
                    "event_id": live_evt.event_id,
                    "case_id": live_evt.case_id,
                    "seq": live_evt.seq,
                    "event_type": str(live_evt.event_type),
                    "actor": live_evt.actor,
                    "payload": live_evt.payload,
                    "ts": live_evt.ts,
                    "prev_hash": live_evt.prev_hash,
                    "hash": live_evt.hash,
                }
                yield (
                    f"id: {live_evt.seq}\n"
                    f"event: {live_evt.event_type}\n"
                    f"data: {canonical_json(live_data)}\n\n"
                )
                yielded_count += 1
                if max_events is not None and yielded_count >= max_events:
                    return

        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            remove_event_listener(on_new_event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
