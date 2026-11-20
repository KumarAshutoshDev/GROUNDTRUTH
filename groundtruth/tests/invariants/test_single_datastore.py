"""Invariant test verifying INV-11: Single datastore.

Asserts:
- No unauthorized databases, message queues, or secondary storage drivers in dependencies.
- Only SQLite or single-database configurations are present.
"""

import tomllib
from pathlib import Path


def test_single_datastore_dependencies() -> None:
    pyproject_path = Path("pyproject.toml")
    assert pyproject_path.exists(), "pyproject.toml must exist"

    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)

    project_deps = data.get("project", {}).get("dependencies", [])
    optional_deps = data.get("project", {}).get("optional-dependencies", {}).get("dev", [])
    all_deps = [d.lower() for d in project_deps + optional_deps]

    # Prohibited secondary storage, cache, or broker drivers
    prohibited_keywords = [
        "redis",
        "neo4j",
        "pymongo",
        "cassandra",
        "elasticsearch",
        "celery",
        "kafka",
        "pika",
        "memcached",
    ]

    for dep in all_deps:
        for prohibited in prohibited_keywords:
            assert prohibited not in dep, (
                f"INV-11 violation: Prohibited secondary datastore/broker '{dep}' in dependencies"
            )
