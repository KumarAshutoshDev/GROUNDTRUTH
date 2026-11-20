"""Orchestrator: Stateless dispatch loop coordinating specialized agents.

Enforces:
- Architecture Section 13: Orchestrator Contract.
  - POST /transition to INVESTIGATING on first dispatch.
  - loop: d = GET /decision.
  - If d.signal in (AUTO_FIX, ESCALATE): POST /transition to CONCLUDED; stop.
  - For item in d.missing_checks + d.rework_queue: dispatch(agent_for(item)).
- CASE-1: Conclusion pointer tracking.
- INV-5: Identity bound to orchestrator token.
"""

from typing import Any

from groundtruth.agents.intel_agent import IntelAgent
from groundtruth.agents.log_agent import LogAgent
from groundtruth.agents.repo_agent import RepoAgent


class Orchestrator:
    """Stateless orchestrator that drives investigation based strictly on /decision."""

    def __init__(
        self,
        client: Any,
        tokens: dict[str, str],
        case_id: str,
        max_iterations: int = 10,
    ) -> None:
        self.client = client
        self.tokens = tokens
        self.case_id = case_id
        self.max_iterations = max_iterations
        self.orch_token = tokens["orchestrator"]
        self.headers = {"Authorization": f"Bearer {self.orch_token}"}

    def transition(self, to_state: str) -> dict[str, Any]:
        """Transition case state via POST /cases/{id}/transition."""
        res = self.client.post(
            f"/cases/{self.case_id}/transition",
            headers=self.headers,
            json={"to": to_state},
        )
        if res.status_code != 200:
            raise RuntimeError(f"Transition to '{to_state}' failed: {res.status_code} {res.text}")
        return res.json()  # type: ignore[no-any-return]

    def get_decision(self) -> dict[str, Any]:
        """Query deterministic case decision via GET /cases/{id}/decision (Architecture 13)."""
        res = self.client.get(
            f"/cases/{self.case_id}/decision",
            headers=self.headers,
        )
        if res.status_code != 200:
            raise RuntimeError(f"Get decision failed: {res.status_code} {res.text}")
        return res.json()  # type: ignore[no-any-return]

    def dispatch_agent_for(self, item: str) -> list[dict[str, Any]]:
        """Map required item to specialist agent and execute investigation."""
        if item in ("log_anomaly", "pod_status", "negative_check"):
            agent = LogAgent(
                client=self.client,
                token=self.tokens["log_agent"],
                case_id=self.case_id,
            )
            return agent.investigate()

        elif item in ("commit_change", "dependency_bump", "cicd_root_cause"):
            agent = RepoAgent(
                client=self.client,
                token=self.tokens["repo_agent"],
                case_id=self.case_id,
            )
            return agent.investigate()

        elif item == "intel_match":
            agent = IntelAgent(
                client=self.client,
                token=self.tokens["intel_agent"],
                case_id=self.case_id,
            )
            return agent.investigate()

        return []

    def run(self) -> dict[str, Any]:
        """Execute orchestrator loop until case reaches AUTO_FIX or ESCALATE."""
        # 1. Transition OPEN -> INVESTIGATING on first dispatch (Architecture 13)
        self.transition("INVESTIGATING")

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            # 2. Query decision
            decision = self.get_decision()
            signal = decision.get("signal")

            # 3. Stop condition: AUTO_FIX or ESCALATE concludes case
            if signal in ("AUTO_FIX", "ESCALATE"):
                self.transition("CONCLUDED")
                return decision

            # 4. Dispatch needed agents for missing checks and rework queue
            missing = decision.get("missing_checks", [])
            rework = decision.get("rework_queue", [])
            targets = list(dict.fromkeys(missing + rework))

            dispatched_any = False
            for target in targets:
                # Re-verify target is still required before dispatching
                cur_dec = self.get_decision()
                cur_needed = cur_dec.get("missing_checks", []) + cur_dec.get("rework_queue", [])
                if target not in cur_needed:
                    continue

                results = self.dispatch_agent_for(target)
                if results:
                    dispatched_any = True

            if not dispatched_any and not missing:
                # No progress possible
                break

        # Fallback decision check
        final_decision = self.get_decision()
        if final_decision.get("signal") in ("AUTO_FIX", "ESCALATE"):
            self.transition("CONCLUDED")
        return final_decision
