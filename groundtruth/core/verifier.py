"""Adversarial Verifier: Independent falsification verification component.

Enforces:
- INV-4: Fail closed. Verifier timeout, malformed JSON, or error returns
  INSUFFICIENT/QUARANTINE, never ADMIT.
- INV-12: The Verifier never sees proposer reasoning or ancestor value text.
  Input is strictly the claim plus raw evidence content.
- LLM-3: Strict JSON output parsed with Pydantic at temperature 0.
- LLM-4: Hard 8-second timeout.
- LLM-5: In-process caching keyed by sha256(claim + evidence_content + prompt_version).
  Only valid verdicts are cached; timeouts and errors never are.
"""

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from groundtruth.adapters.llm import LLMAdapter, VerifierOutput
from groundtruth.core.utils import canonical_json

PROMPT_VERSION = "v1"
PROMPT_FILE = Path("groundtruth/prompts/verifier_v1.txt")


class VerifierCache:
    """In-process LRU cache for fixture-identical claims (LLM-5)."""

    def __init__(self, max_size: int = 1000) -> None:
        self.max_size = max_size
        self._cache: dict[str, VerifierOutput] = {}

    def get(self, key: str) -> VerifierOutput | None:
        return self._cache.get(key)

    def set(self, key: str, value: VerifierOutput) -> None:
        if len(self._cache) >= self.max_size:
            # Simple eviction of oldest item
            first_key = next(iter(self._cache))
            del self._cache[first_key]
        self._cache[key] = value

    def clear(self) -> None:
        self._cache.clear()


# Global in-process cache
_global_verifier_cache = VerifierCache()


def compute_cache_key(claim_data: Mapping[str, Any], evidence_content: str) -> str:
    """Compute sha256(claim + evidence_content + prompt_version) (LLM-5)."""
    serialized_claim = canonical_json(claim_data)
    key_material = f"{serialized_claim}|{evidence_content}|{PROMPT_VERSION}"
    return hashlib.sha256(key_material.encode("utf-8")).hexdigest()


def build_verifier_prompt(claim_text: str, evidence_content: str) -> str:
    """Construct the adversarial falsification prompt wrapping data in delimiters (LLM-7)."""
    if PROMPT_FILE.exists():
        template = PROMPT_FILE.read_text(encoding="utf-8")
        return template.replace("{claim_text}", claim_text).replace(
            "{evidence_content}", evidence_content
        )

    # Fallback template if file not found
    return (
        "Attempt to falsify the claim against raw evidence. Return strict JSON with "
        "verdict (SUPPORTED/REFUTED/INSUFFICIENT), rationale, and evidence_quotes.\n\n"
        f"<CLAIM>\n{claim_text}\n</CLAIM>\n\n"
        f"<RAW_EVIDENCE>\n{evidence_content}\n</RAW_EVIDENCE>\n"
    )


def verify_claim(
    claim_data: dict[str, Any],
    evidence_content: str,
    adapter: LLMAdapter,
    timeout: float = 8.0,
    cache: VerifierCache | None = None,
) -> VerifierOutput:
    """Adversarially evaluate a claim against raw evidence with fail-closed guarantee (INV-4)."""
    active_cache = cache or _global_verifier_cache
    cache_key = compute_cache_key(claim_data, evidence_content)

    # Check in-process cache
    cached = active_cache.get(cache_key)
    if cached is not None:
        return cached.model_copy(update={"tokens_in": 0, "tokens_out": 0, "cache_hit": True})

    # Format claim text without any proposer reasoning or auxiliary chatter
    claim_text = canonical_json(claim_data.get("value", claim_data))
    prompt = build_verifier_prompt(claim_text=claim_text, evidence_content=evidence_content)

    try:
        llm_res = adapter.complete(prompt, timeout=timeout)
        parsed = VerifierOutput.model_validate_json(llm_res.text)

        # Ensure verdict is valid
        if parsed.verdict not in ("SUPPORTED", "REFUTED", "INSUFFICIENT"):
            raise ValueError(f"Invalid verdict: {parsed.verdict}")

        parsed = parsed.model_copy(
            update={
                "tokens_in": llm_res.tokens_in,
                "tokens_out": llm_res.tokens_out,
                "cache_hit": False,
            }
        )

        # Cache ONLY valid results (LLM-5)
        active_cache.set(cache_key, parsed)
        return parsed

    except Exception as e:
        # INV-4: Fail closed. Timeout, parse error, or exception MUST yield QUARANTINE
        return VerifierOutput(
            verdict="INSUFFICIENT",
            rationale=f"verifier_unavailable: {type(e).__name__}: {e}",
            evidence_quotes=[],
        )
