"""Unit tests verifying canonical JSON and clock/ID injection utilities."""

import hashlib
from datetime import UTC, datetime

from groundtruth.core.utils import (
    DeterministicIdGenerator,
    FixtureClock,
    SystemClock,
    UUIDGenerator,
    canonical_json,
)


def test_canonical_json_key_sorting() -> None:
    dict1 = {"b": 1, "a": 2, "c": {"z": 26, "y": 25}}
    dict2 = {"a": 2, "c": {"y": 25, "z": 26}, "b": 1}

    json1 = canonical_json(dict1)
    json2 = canonical_json(dict2)

    assert json1 == json2
    assert json1 == '{"a":2,"b":1,"c":{"y":25,"z":26}}'

    hash1 = hashlib.sha256(json1.encode("utf-8")).hexdigest()
    hash2 = hashlib.sha256(json2.encode("utf-8")).hexdigest()
    assert hash1 == hash2


def test_canonical_json_datetime_formatting() -> None:
    dt = datetime(2026, 11, 19, 10, 30, 0, tzinfo=UTC)
    payload = {"timestamp": dt, "val": 42}

    serialized = canonical_json(payload)
    assert serialized == '{"timestamp":"2026-11-19T10:30:00Z","val":42}'


def test_system_clock() -> None:
    clock = SystemClock()
    now = clock.now()
    assert now.tzinfo is not None
    assert now.tzinfo == UTC


def test_fixture_clock() -> None:
    clock = FixtureClock("2026-11-19T12:00:00Z")
    assert clock.now() == datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC)

    clock.advance(60)
    assert clock.now() == datetime(2026, 11, 19, 12, 1, 0, tzinfo=UTC)

    clock.set_time("2026-11-19T13:00:00Z")
    assert clock.now() == datetime(2026, 11, 19, 13, 0, 0, tzinfo=UTC)


def test_id_generators() -> None:
    uuid_gen = UUIDGenerator()
    id1 = uuid_gen.generate("evt")
    id2 = uuid_gen.generate("evt")
    assert id1.startswith("evt_")
    assert id2.startswith("evt_")
    assert id1 != id2

    det_gen = DeterministicIdGenerator()
    d1 = det_gen.generate("fact")
    d2 = det_gen.generate("fact")
    d3 = det_gen.generate("case")
    assert d1 == "fact_0001"
    assert d2 == "fact_0002"
    assert d3 == "case_0001"
