"""Utility functions and protocols for GroundTruth.

Includes:
- canonical_json: Deterministic JSON serialization for hashing
- Clock: Protocol and implementations for time injection
- IdGenerator: Protocol and implementations for ID generation
"""

import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol


def _json_default(obj: Any) -> Any:
    """Normalize objects for canonical JSON serialization."""
    if isinstance(obj, datetime):
        # Convert to UTC and format as ISO 8601 with Z suffix
        utc_dt = obj if obj.tzinfo is not None else obj.replace(tzinfo=UTC)
        utc_dt = utc_dt.astimezone(UTC)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if hasattr(obj, "model_dump"):
        # Pydantic v2 support
        return obj.model_dump(mode="json")
    if hasattr(obj, "dict"):
        # Pydantic v1 support
        return obj.dict()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _sort_recursively(obj: Any) -> Any:
    """Recursively sort dict keys for canonical representation."""
    if isinstance(obj, Mapping):
        sorted_items = sorted(obj.items(), key=lambda item: str(item[0]))
        return {k: _sort_recursively(v) for k, v in sorted_items}
    if isinstance(obj, Sequence) and not isinstance(obj, str | bytes | bytearray):
        return [_sort_recursively(item) for item in obj]
    return obj


def canonical_json(obj: Any) -> str:
    """Serialize an object into canonical JSON.

    Properties:
    - Sorted dictionary keys
    - UTF-8 encoding
    - No superfluous whitespace (separators=(',', ':'))
    - ISO 8601 UTC timestamps
    """
    sorted_obj = _sort_recursively(obj)
    return json.dumps(
        sorted_obj,
        default=_json_default,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


class Clock(Protocol):
    """Protocol for time injection."""

    def now(self) -> datetime:
        """Return current datetime in UTC."""
        ...


class SystemClock:
    """System clock using current wall time."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixtureClock:
    """Injected fixture clock for reproducible evaluation and demo runs."""

    def __init__(self, current_time: datetime | str) -> None:
        if isinstance(current_time, str):
            # Parse ISO 8601 string
            parsed = datetime.fromisoformat(current_time.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            self._current_time = parsed.astimezone(UTC)
        else:
            if current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=UTC)
            self._current_time = current_time.astimezone(UTC)

    def now(self) -> datetime:
        return self._current_time

    def set_time(self, new_time: datetime | str) -> None:
        if isinstance(new_time, str):
            parsed = datetime.fromisoformat(new_time.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            self._current_time = parsed.astimezone(UTC)
        else:
            if new_time.tzinfo is None:
                new_time = new_time.replace(tzinfo=UTC)
            self._current_time = new_time.astimezone(UTC)

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._current_time += timedelta(seconds=seconds)


class IdGenerator(Protocol):
    """Protocol for ID generation."""

    def generate(self, prefix: str = "") -> str:
        """Generate a unique ID."""
        ...


class UUIDGenerator:
    """Standard random UUID generator."""

    def generate(self, prefix: str = "") -> str:
        unique_id = uuid.uuid4().hex
        return f"{prefix}_{unique_id}" if prefix else unique_id


class DeterministicIdGenerator:
    """Deterministic counter-based ID generator for testing and replay verification."""

    def __init__(self, prefix: str = "id") -> None:
        self._default_prefix = prefix
        self._counters: dict[str, int] = {}

    def generate(self, prefix: str = "") -> str:
        p = prefix or self._default_prefix
        count = self._counters.get(p, 0) + 1
        self._counters[p] = count
        return f"{p}_{count:04d}"
