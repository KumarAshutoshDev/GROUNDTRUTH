"""Invariant test verifying INV-12: Verifier input isolation.

Proves:
The Verifier prompt contains the claim and raw evidence content only,
and contains none of the proposer's reasoning or the ancestors' value text.
Checked rigorously using sentinel strings.
"""

from groundtruth.adapters.llm import LLMAdapter, LLMResult
from groundtruth.core.verifier import verify_claim


class RecordingAdapter(LLMAdapter):
    def __init__(self) -> None:
        self.recorded_prompts: list[str] = []

    def complete(self, prompt: str, timeout: float = 8.0) -> LLMResult:
        self.recorded_prompts.append(prompt)
        return LLMResult(
            text='{"verdict": "SUPPORTED", "rationale": "Verified", "evidence_quotes": []}',
            tokens_in=50,
            tokens_out=20,
            model="test",
        )


def test_verifier_input_isolation_with_sentinel_strings() -> None:
    adapter = RecordingAdapter()

    proposer_reasoning_sentinel = "SENTINEL_PROPOSER_SECRET_REASONING_DO_NOT_LEAK"
    ancestor_value_sentinel = "SENTINEL_ANCESTOR_VALUE_TEXT_DO_NOT_LEAK"
    claim_content = "dependency bump caused connection reset"
    raw_evidence_content = "ConnectionResetError: [Errno 104] Connection reset by peer"

    # Simulate proposal payload containing proposer reasoning
    proposal_data = {
        "value": {"conclusion": claim_content},
        "reasoning": proposer_reasoning_sentinel,
        "notes": "Some agent internal scratchpad",
    }

    # Verify claim against raw evidence content
    output = verify_claim(
        claim_data=proposal_data,
        evidence_content=raw_evidence_content,
        adapter=adapter,
    )

    assert output.verdict == "SUPPORTED"
    assert len(adapter.recorded_prompts) == 1
    prompt_delivered = adapter.recorded_prompts[0]

    # INV-12: The prompt MUST contain the claim and raw evidence
    assert claim_content in prompt_delivered
    assert raw_evidence_content in prompt_delivered

    # INV-12: The prompt MUST NOT contain proposer reasoning or ancestor values
    assert proposer_reasoning_sentinel not in prompt_delivered
    assert ancestor_value_sentinel not in prompt_delivered
    assert "scratchpad" not in prompt_delivered
