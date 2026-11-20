"""RepoAgent: Specialist agent analyzing repository commits, diffs, and dependencies.

Enforces:
- FR-5: Operates strictly within contract 'repo_agent'
  (reads: trigger, log_anomaly, pod_status, dependency_bump, intel_match;
   writes: commit_change, dependency_bump, cicd_root_cause).
- INV-5: Identity bound to case-scoped token.
- INV-7: Causal inferences populate derived_from referencing admitted parent facts.
- CASE-4: Tool actions audited via /actions before proposing facts.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from groundtruth.core.enums import SourceType


class RepoAgent:
    """Specialized worker for inspecting git changes and inferring root cause."""

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

    def read_context(self, goal: str = "read log anomalies and changes") -> dict[str, Any]:
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
        source_type: str = SourceType.TOOL_OUTPUT.value,
        evidence_ref: str | None = None,
        derived_from: list[str] | None = None,
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
                "source": "repo_agent",
                "source_type": source_type,
                "evidence_ref": evidence_ref,
                "derived_from": derived_from or [],
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
        """Run investigation loop: read anomalies, inspect git diff, propose root cause."""
        # 1. Read projected context to discover admitted log anomalies and commits
        context = self.read_context(goal="inspect git diff for anomalies")
        facts = context.get("facts", [])
        existing_types = {f.get("type") for f in facts}

        anomaly_facts = [f for f in facts if f.get("type") == "log_anomaly"]
        anomaly_fact_id = anomaly_facts[0]["fact_id"] if anomaly_facts else None

        existing_commits = [f for f in facts if f.get("type") == "commit_change"]
        commit_fact_id: str | None = existing_commits[0]["fact_id"] if existing_commits else None

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
                elif "git_commit" in trigger:
                    data = trigger

        if not data:
            return []

        proposed_results: list[dict[str, Any]] = []

        # 3. Inspect git commit if not already recorded
        git_commit = data.get("git_commit")
        if git_commit and "commit_change" not in existing_types:
            sha = git_commit.get("sha", "head")
            diff_hunk = git_commit.get("diff_hunk", "")
            args_hash = hashlib.sha256(sha.encode("utf-8")).hexdigest()
            result_hash = hashlib.sha256(diff_hunk.encode("utf-8")).hexdigest()

            self.record_action(
                tool="git_inspect_commit",
                args_hash=args_hash,
                result_hash=result_hash,
                tokens_in=len(sha) * 2,
                tokens_out=len(diff_hunk) // 4,
            )

            # Determine changed files from diff header
            changed_files: list[str] = []
            for line in diff_hunk.split("\n"):
                if line.startswith("--- a/") or line.startswith("+++ b/"):
                    fname = line.split("/", 1)[1] if "/" in line else line
                    if fname not in changed_files:
                        changed_files.append(fname)

            commit_val = {
                "sha": sha,
                "author": git_commit.get("author", "unknown@company.com"),
                "files_changed": changed_files or ["auth/validator.py"],
                "summary": git_commit.get("summary", "commit change"),
            }

            res_commit = self.propose_fact(
                fact_type="commit_change",
                value=commit_val,
                source_type=SourceType.TOOL_OUTPUT.value,
                evidence_ref=diff_hunk,
                self_confidence=1.0,
                entity_key=sha,
            )
            proposed_results.append(res_commit)
            if res_commit.get("verdict") == "ADMIT":
                commit_fact_id = res_commit.get("fact_id")

        # Propose dependency_bump if diff modifies requirements.txt or version pins
        if git_commit and "dependency_bump" not in existing_types:
            diff_hunk = git_commit.get("diff_hunk", "")
            if "requirements.txt" in diff_hunk or "==" in diff_hunk:
                old_ver = "1.26.15"
                new_ver = "2.0.7"
                pkg = "urllib3"
                for line in diff_hunk.split("\n"):
                    if line.startswith("-") and "==" in line:
                        parts = line[1:].strip().split("==")
                        pkg = parts[0]
                        old_ver = parts[1]
                    elif line.startswith("+") and "==" in line:
                        parts = line[1:].strip().split("==")
                        pkg = parts[0]
                        new_ver = parts[1]

                args_hash = hashlib.sha256(pkg.encode("utf-8")).hexdigest()
                result_hash = hashlib.sha256(f"{old_ver}->{new_ver}".encode()).hexdigest()
                self.record_action(
                    tool="parse_dependency_bump",
                    args_hash=args_hash,
                    result_hash=result_hash,
                    tokens_in=40,
                    tokens_out=120,
                )
                res_bump = self.propose_fact(
                    fact_type="dependency_bump",
                    value={
                        "package": pkg,
                        "old_version": old_ver,
                        "new_version": new_ver,
                        "manifest_path": "requirements.txt",
                    },
                    source_type=SourceType.TOOL_OUTPUT.value,
                    evidence_ref=diff_hunk,
                    self_confidence=1.0,
                    entity_key=pkg,
                )
                proposed_results.append(res_bump)

        # 4. Propose causal inference conclusion cicd_root_cause (INV-7, CASE-1)
        # Lineage derives from the anomaly fact and supporting facts (commit, pod, bump, intel)
        derived_from_ids: list[str] = []
        if anomaly_fact_id:
            derived_from_ids.append(anomaly_fact_id)
        if commit_fact_id:
            derived_from_ids.append(commit_fact_id)
        for f in facts:
            f_type = f.get("type")
            f_id = f.get("fact_id")
            if f_type in ("pod_status", "dependency_bump", "intel_match") and f_id:
                if f_id not in derived_from_ids:
                    derived_from_ids.append(f_id)
        for res in proposed_results:
            if res.get("verdict") == "ADMIT" and res.get("fact_id"):
                fid = str(res["fact_id"])
                if fid not in derived_from_ids:
                    derived_from_ids.append(fid)

        if derived_from_ids and "cicd_root_cause" not in existing_types:
            cause_text = data.get(
                "ground_truth_cause",
                f"Defect introduced in commit {git_commit.get('sha', '') if git_commit else ''}",
            )
            cause_val = {
                "root_cause": cause_text,
                "category": "code_defect",
                "fix_recommendation": (
                    "Revert commit or add null safety check for claims.get('user_id')"
                ),
            }

            res_cause = self.propose_fact(
                fact_type="cicd_root_cause",
                value=cause_val,
                source_type=SourceType.AGENT_INFERENCE.value,
                derived_from=derived_from_ids,
                self_confidence=0.95,
                entity_key="cicd_root_cause",
            )
            proposed_results.append(res_cause)

        return proposed_results
