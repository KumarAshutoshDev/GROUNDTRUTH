"""Invariant test verifying INV-4: Fail closed.

Proves:
Verifier timeout, malformed output, and exceptions MUST result in
INSUFFICIENT / QUARANTINE, never ADMIT.
"""

from groundtruth.adapters.llm import LLMAdapter, LLMResult
from groundtruth.core.verifier import VerifierCache, verify_claim


class TimeoutFailingAdapter(LLMAdapter):
    def complete(self, prompt: str, timeout: float = 8.0) -> LLMResult:
        raise TimeoutError("Model request timed out after 8.0s")


class MalformedJsonAdapter(LLMAdapter):
    def complete(self, prompt: str, timeout: float = 8.0) -> LLMResult:
        return LLMResult(
            text="I think the claim is true but here is invalid json {",
            tokens_in=10,
            tokens_out=15,
            model="test",
        )


class BadVerdictAdapter(LLMAdapter):
    def complete(self, prompt: str, timeout: float = 8.0) -> LLMResult:
        return LLMResult(
            text='{"verdict": "MAYBE_TRUE", "rationale": "Uncertain", "evidence_quotes": []}',
            tokens_in=10,
            tokens_out=15,
            model="test",
        )


def test_fail_closed_on_timeout() -> None:
    cache = VerifierCache()
    adapter = TimeoutFailingAdapter()
    output = verify_claim(
        claim_data={"value": {"status": "broken"}},
        evidence_content="raw log excerpt",
        adapter=adapter,
        cache=cache,
    )
    assert output.verdict == "INSUFFICIENT"
    assert "verifier_unavailable" in output.rationale
    # Verify timeout error is NEVER cached (LLM-5)
    assert len(cache._cache) == 0


def test_fail_closed_on_malformed_json() -> None:
    cache = VerifierCache()
    adapter = MalformedJsonAdapter()
    output = verify_claim(
        claim_data={"value": {"status": "broken"}},
        evidence_content="raw log excerpt",
        adapter=adapter,
        cache=cache,
    )
    assert output.verdict == "INSUFFICIENT"
    assert "verifier_unavailable" in output.rationale
    assert len(cache._cache) == 0


def test_fail_closed_on_bad_verdict() -> None:
    cache = VerifierCache()
    adapter = BadVerdictAdapter()
    output = verify_claim(
        claim_data={"value": {"status": "broken"}},
        evidence_content="raw log excerpt",
        adapter=adapter,
        cache=cache,
    )
    assert output.verdict == "INSUFFICIENT"
    assert "verifier_unavailable" in output.rationale
    assert len(cache._cache) == 0
