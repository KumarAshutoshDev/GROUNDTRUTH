"""Main FastAPI application entry point for GroundTruth."""

import sqlite3
from collections.abc import Generator
from pathlib import Path

from fastapi import FastAPI, Request

from groundtruth.api.actions import router as actions_router
from groundtruth.api.cases import get_clock, get_db
from groundtruth.api.cases import router as cases_router
from groundtruth.api.decision import router as decision_router
from groundtruth.api.graph import router as graph_router
from groundtruth.api.metrics import router as metrics_router
from groundtruth.api.negative import router as negative_router
from groundtruth.api.override import router as override_router
from groundtruth.api.propose import router as propose_router
from groundtruth.api.read import router as read_router
from groundtruth.api.stream import router as stream_router
from groundtruth.api.transition import router as transition_router
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.utils import Clock

# Default DB location (can be file or in-memory)
DEFAULT_DB_PATH = Path("groundtruth.db")


def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Dependency provider for database connections.

    Yields a dedicated per-request connection to ensure thread safety
    under concurrent ASGI requests (e.g., SSE streaming alongside dashboard fetches).
    """
    conn = get_connection(DEFAULT_DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def create_app(
    db_conn: sqlite3.Connection | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    """Factory creating and configuring the FastAPI app."""
    app = FastAPI(
        title="GroundTruth",
        description="The shared brain that agents can actually trust: governed context layer",
        version="0.1.0",
    )

    if db_conn is not None:
        app.dependency_overrides[get_db] = lambda: db_conn
    else:
        init_conn = get_connection(DEFAULT_DB_PATH)
        try:
            init_db(init_conn)
        finally:
            init_conn.close()
        app.dependency_overrides[get_db] = get_db_connection

    if clock is not None:
        app.dependency_overrides[get_clock] = lambda: clock

    app.include_router(cases_router)
    app.include_router(propose_router)
    app.include_router(actions_router)
    app.include_router(read_router)
    app.include_router(transition_router)
    app.include_router(decision_router)
    app.include_router(graph_router)
    app.include_router(negative_router)
    app.include_router(override_router)
    app.include_router(stream_router)
    app.include_router(metrics_router)

    dashboard_dir = Path("groundtruth/dashboard")
    if dashboard_dir.exists():
        from fastapi.responses import FileResponse
        from starlette.staticfiles import StaticFiles

        app.mount(
            "/dashboard",
            StaticFiles(directory=str(dashboard_dir), html=True),
            name="dashboard",
        )

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(dashboard_dir / "index.html")

    @app.middleware("http")
    async def add_no_cache_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        if request.url.path.startswith("/dashboard") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    return app


app = create_app()
