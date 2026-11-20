"""IntelAgent: Specialist agent querying threat intelligence and package advisory databases.

Enforces:
- FR-5: Operates strictly within contract 'intel_agent'
  (reads: log_anomaly, dependency_bump; writes: intel_match).
- INV-5: Identity bound to case-scoped token.
- CASE-4: Tool actions audited via /actions before proposing facts.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from groundtruth.core.enums import SourceType
from groundtruth.core.utils import canonical_json


class IntelAgent:
    """Specialized worker for correlating package versions with advisory registries."""

    def __init__(self, client: Any, token: str, case_id: str) -> None:
        self.client = client
        self.token = token
        self.case_id = case_id
        self.headers = {"Authorization": f"Bearer {token}"}

    def record_action(
        self,
        tool: str,
        args_hash: str,
        result_hash: str,
        tokens_in: int = 100,
        tokens_out: int = 200,
        cache_hit: bool = False,
    ) -> dict[str, Any]:
        """Record an audited agent action via POST /cases/{id}/actions (CASE-4)."""
        res = self.client.post(
            f"/cases/{self.case_id}/actions",
            headers=self.headers,
            json={
                "tool": tool,
                "args_hash": args_hash,
                "result_hash": result_hash,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cache_hit": cache_hit,
            },
        )
        if res.status_code != 200:
            raise RuntimeError(f"Action recording failed: {res.status_code} {res.text}")
        return res.json()  # type: ignore[no-any-return]

    def read_context(
        self, goal: str = "query advisory database for dependencies"
    ) -> dict[str, Any]:
        """Read projected case context via POST /cases/{id}/read (FR-5)."""
        res = self.client.post(
            f"/cases/{self.case_id}/read",
            headers=self.headers,
            json={"goal": goal},
        )
        if res.status_code != 200:
            raise RuntimeError(f"Read context failed: {res.status_code} {res.text}")
        return res.json()  # type: ignore[no-any-return]

    def propose_fact(
        self,
        fact_type: str,
        value: dict[str, Any],
        source_type: str = SourceType.DOCUMENT.value,
        evidence_ref: str | None = None,
        self_confidence: float = 1.0,
        entity_key: str | None = None,
    ) -> dict[str, Any]:
        """Submit proposed fact to Write Gate via POST /cases/{id}/propose."""
        res = self.client.post(
            f"/cases/{self.case_id}/propose",
            headers=self.headers,
            json={
                "type": fact_type,
                "value": value,
                "source": "intel_agent",
                "source_type": source_type,
                "evidence_ref": evidence_ref,
                "self_confidence": self_confidence,
                "entity_key": entity_key,
            },
        )
        if res.status_code != 200:
            raise RuntimeError(f"Propose fact failed: {res.status_code} {res.text}")
        return res.json()  # type: ignore[no-any-return]

    def load_fixture_data(self, fixture_name_or_dict: str | dict[str, Any]) -> dict[str, Any]:
        """Load fixture file if string or return dict."""
        if isinstance(fixture_name_or_dict, dict):
            return fixture_name_or_dict

        p = Path("groundtruth/packs/cicd/fixtures")
        candidates = [
            p / f"{fixture_name_or_dict}.json",
            p / fixture_name_or_dict,
        ]
        for c in candidates:
            if c.exists() and c.is_file():
                with open(c, encoding="utf-8") as f:
                    return json.load(f)  # type: ignore[no-any-return]

        for fpath in p.glob("*.json"):
            try:
                with open(fpath, encoding="utf-8") as f:
                    content = json.load(f)
                    if (
                        content.get("fixture_id") == fixture_name_or_dict
                        or fpath.stem in fixture_name_or_dict
                        or fixture_name_or_dict in fpath.stem
                    ):
                        return content  # type: ignore[no-any-return]
            except Exception:
                continue

        raise FileNotFoundError(f"Fixture '{fixture_name_or_dict}' not found in {p}")

    def investigate(self, fixture_data: str | dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Run investigation loop: query advisories for dependencies and propose intel_match."""
        # 1. Read projected context (finds dependency_bump or log_anomaly)
        self.read_context(goal="check advisories for packages")

        # 2. Resolve fixture data
        data: dict[str, Any] | None = None
        if fixture_data is not None:
            data = self.load_fixture_data(fixture_data)
        else:
            res = self.client.get(f"/cases/{self.case_id}")
            if res.status_code == 200:
                c_data = res.json()
                trigger = c_data.get("trigger", {})
                if "fixture_id" in trigger:
                    data = self.load_fixture_data(trigger["fixture_id"])
                elif "intel_advisory" in trigger:
                    data = trigger

        if not data:
            return []

        proposed_results: list[dict[str, Any]] = []

        # 3. Check for intel_advisory in fixture
        advisory = data.get("intel_advisory")
        if advisory:
            pkg = advisory.get("package", "unknown")
            args_hash = hashlib.sha256(pkg.encode("utf-8")).hexdigest()
            result_hash = hashlib.sha256(canonical_json(advisory).encode("utf-8")).hexdigest()

            # Record tool call action
            self.record_action(
                tool="query_advisory_registry",
                args_hash=args_hash,
                result_hash=result_hash,
                tokens_in=50,
                tokens_out=150,
            )

            # Propose intel_match fact
            adv_id = advisory.get("advisory_id", "ADV-001")
            val = {
                "advisory_id": adv_id,
                "package": pkg,
                "severity": advisory.get("severity", "MODERATE"),
                "affected_versions": advisory.get("affected_versions", ">=1.0"),
                "url": f"https://github.com/advisories/{adv_id}",
            }
            summary = advisory.get("summary", f"Advisory {adv_id} for {pkg}")

            res = self.propose_fact(
                fact_type="intel_match",
                value=val,
                source_type=SourceType.DOCUMENT.value,
                evidence_ref=summary,
                self_confidence=1.0,
                entity_key=adv_id,
            )
            proposed_results.append(res)

        return proposed_results
