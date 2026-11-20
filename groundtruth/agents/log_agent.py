"""LogAgent: Specialist agent analyzing CI/CD logs, stack traces, and pod health.

Enforces:
- FR-5: Operates strictly within contract 'log_agent' (reads: trigger, pod_status;
  writes: log_anomaly, pod_status, negative_check).
- INV-5: Identity bound to case-scoped token.
- CASE-4: Tool actions audited via /actions before proposing facts.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from groundtruth.core.enums import SourceType
from groundtruth.core.utils import canonical_json


class LogAgent:
    """Specialized worker for diagnosing CI/CD build logs and pod anomalies."""

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

    def read_context(self, goal: str = "find log anomalies") -> dict[str, Any]:
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
        evidence_ref: str,
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
                "source": "log_agent",
                "source_type": SourceType.TOOL_OUTPUT.value,
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

        # Scan all fixture files matching fixture_id or filename stems
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
        """Run standard investigation loop for LogAgent on the case."""
        # 1. Read projected context
        context = self.read_context(goal="inspect build logs and pod health")
        existing_types = {f.get("type") for f in context.get("facts", [])}
        has_negative = len(context.get("negative_checks", [])) > 0

        # 2. Resolve fixture data
        data: dict[str, Any] | None = None
        if fixture_data is not None:
            data = self.load_fixture_data(fixture_data)
        else:
            # Try reading case trigger
            res = self.client.get(f"/cases/{self.case_id}")
            if res.status_code == 200:
                c_data = res.json()
                trigger = c_data.get("trigger", {})
                if "fixture_id" in trigger:
                    data = self.load_fixture_data(trigger["fixture_id"])
                elif "build_log" in trigger:
                    data = trigger

        if not data:
            return []

        proposed_results: list[dict[str, Any]] = []

        # 3. Analyze build_log if log_anomaly not already recorded
        build_log = data.get("build_log", "")
        if build_log and "log_anomaly" not in existing_types:
            pipe_id = data.get("pipeline_id", "build_log")
            args_hash = hashlib.sha256(pipe_id.encode("utf-8")).hexdigest()
            result_hash = hashlib.sha256(build_log.encode("utf-8")).hexdigest()

            # Record tool call action
            self.record_action(
                tool="fetch_build_log",
                args_hash=args_hash,
                result_hash=result_hash,
                tokens_in=len(args_hash) * 2,
                tokens_out=len(build_log) // 4,
            )

            # Detect error lines and stack traces
            lines = build_log.split("\n")
            error_msg: str | None = None
            stack_lines: list[str] = []
            component = "build_system"
            in_traceback = False

            for line in lines:
                s_line = line.strip()
                if "auth-service" in s_line:
                    component = "auth-service"
                if "FAILED" in s_line or "ERROR" in s_line:
                    if error_msg is None:
                        error_msg = s_line
                if "Traceback" in s_line:
                    in_traceback = True
                if in_traceback:
                    stack_lines.append(s_line)
                    is_err = "Error" in s_line or "Exception" in s_line
                    if is_err and not s_line.startswith("Traceback"):
                        in_traceback = False

            if error_msg:
                # Propose log_anomaly fact
                val = {
                    "message": error_msg,
                    "level": "ERROR",
                    "component": component,
                    "stack_trace": "\n".join(stack_lines) if stack_lines else error_msg,
                }
                res = self.propose_fact(
                    fact_type="log_anomaly",
                    value=val,
                    evidence_ref=build_log,
                    self_confidence=1.0,
                    entity_key=component,
                )
                proposed_results.append(res)

        # 4. Analyze k8s_events / pod_status / negative_checks
        pod_status_data = data.get("pod_status")
        if pod_status_data and "pod_status" not in existing_types:
            pod_name = pod_status_data.get("pod_name", "runner-pod-07")
            args_hash = hashlib.sha256(canonical_json(pod_status_data).encode("utf-8")).hexdigest()
            self.record_action(
                tool="inspect_pod_status",
                args_hash=args_hash,
                result_hash=args_hash,
                tokens_in=50,
                tokens_out=150,
            )
            res_pod = self.propose_fact(
                fact_type="pod_status",
                value={
                    "pod_name": pod_name,
                    "namespace": pod_status_data.get("namespace", "ci-runners"),
                    "status": pod_status_data.get("status", "OOMKilled"),
                    "exit_code": pod_status_data.get("exit_code", 137),
                },
                evidence_ref=(
                    f"Pod {pod_name} terminated with status "
                    f"{pod_status_data.get('status', 'OOMKilled')}"
                ),
                self_confidence=1.0,
                entity_key=pod_name,
            )
            proposed_results.append(res_pod)

        k8s_events = data.get("k8s_events", {})
        if k8s_events:
            args_hash = hashlib.sha256(b"k8s_events").hexdigest()
            result_hash = hashlib.sha256(canonical_json(k8s_events).encode("utf-8")).hexdigest()

            if k8s_events.get("oom_killed_found") and "pod_status" not in existing_types:
                self.record_action(
                    tool="query_k8s_events",
                    args_hash=args_hash,
                    result_hash=result_hash,
                    tokens_in=50,
                    tokens_out=150,
                )
                # OOM killed pod found (e.g. Fixture 3)
                pod_name = (
                    k8s_events.get("checked_pods", ["unknown_pod"])[0]
                    if k8s_events.get("checked_pods")
                    else "test-pod-01"
                )
                res = self.propose_fact(
                    fact_type="pod_status",
                    value={
                        "pod_name": pod_name,
                        "namespace": "cicd-tests",
                        "status": "OOMKilled",
                        "exit_code": 137,
                    },
                    evidence_ref=f"k8s pod event: {pod_name} OOMKilled",
                    self_confidence=1.0,
                    entity_key=pod_name,
                )
                proposed_results.append(res)

            elif not k8s_events.get("oom_killed_found") and not has_negative:
                # Ruled out OOM killed pods -> propose negative_check fact (NEG-1, NEG-2)
                checked = k8s_events.get("checked_pods", ["auth-test-pod-01"])
                self.record_action(
                    tool="query_k8s_events",
                    args_hash=args_hash,
                    result_hash=result_hash,
                    tokens_in=50,
                    tokens_out=150,
                )
                evidence = (
                    f"K8s event inspection confirmed 0 pods OOMKilled among {len(checked)} pods"
                )
                res = self.propose_fact(
                    fact_type="negative_check",
                    value={
                        "check_type": "oom_pod_crash",
                        "scope": checked,
                        "window_start": "2026-11-19T09:00:00Z",
                        "window_end": "2026-11-19T10:00:00Z",
                    },
                    evidence_ref=evidence,
                    self_confidence=1.0,
                    entity_key="oom_pod_crash",
                )
                proposed_results.append(res)

        return proposed_results
