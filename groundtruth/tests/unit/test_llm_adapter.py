"""Unit tests verifying LLM adapter and VerifierOutput parsing."""

import json

from groundtruth.adapters.llm import LLMResult, MockFixtureLLMAdapter, VerifierOutput


def test_verifier_output_pydantic_parsing() -> None:
    raw_json = json.dumps(
        {
            "verdict": "SUPPORTED",
            "rationale": "Log line 88 confirms NullPointerException.",
            "evidence_quotes": ["AttributeError: 'NoneType' object has no attribute 'startswith'"],
        }
    )
    output = VerifierOutput.model_validate_json(raw_json)
    assert output.verdict == "SUPPORTED"
    assert "NullPointerException" in output.rationale
    assert len(output.evidence_quotes) == 1


def test_mock_fixture_adapter() -> None:
    adapter = MockFixtureLLMAdapter()
    adapter.set_response(
        "dependency_bump",
        json.dumps(
            {
                "verdict": "REFUTED",
                "rationale": "Evidence does not indicate dependency bump caused the failure.",
                "evidence_quotes": [],
            }
        ),
    )

    res1 = adapter.complete("Please evaluate this dependency_bump claim", timeout=5.0)
    assert isinstance(res1, LLMResult)
    data1 = VerifierOutput.model_validate_json(res1.text)
    assert data1.verdict == "REFUTED"

    res2 = adapter.complete("Generic claim", timeout=5.0)
    data2 = VerifierOutput.model_validate_json(res2.text)
    assert data2.verdict == "SUPPORTED"
