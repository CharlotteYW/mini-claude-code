"""Deterministic faithfulness helper (M36).

Soft LLM-as-judge is optional elsewhere; this checks required answer spans
appear in retrieved evidence texts (case-insensitive substring).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class FaithfulnessResult:
    passed: bool
    missing: tuple[str, ...]
    evidence_chars: int

    def summary(self) -> str:
        if self.passed:
            return f"faithfulness OK (evidence_chars={self.evidence_chars})"
        miss = ", ".join(repr(m) for m in self.missing)
        return f"faithfulness FAIL missing=[{miss}] evidence_chars={self.evidence_chars}"


def check_faithfulness(
    answer: str,
    evidence_texts: Sequence[str],
    *,
    required_spans: Sequence[str] | None = None,
) -> FaithfulnessResult:
    """Pass if every required span is found in the joined evidence.

    If ``required_spans`` is None/empty, derive spans from non-trivial answer
    tokens (length >= 4) — teaching simplification, not production NLI.
    """
    blob = "\n".join(evidence_texts).lower()
    if required_spans:
        spans = [s.strip() for s in required_spans if s and s.strip()]
    else:
        spans = [
            tok.strip(".,;:!?\"'()[]{}").lower()
            for tok in answer.split()
            if len(tok.strip(".,;:!?\"'()[]{}")) >= 4
        ]
        # de-dupe preserve order
        seen: set[str] = set()
        uniq: list[str] = []
        for s in spans:
            if s not in seen:
                seen.add(s)
                uniq.append(s)
        spans = uniq

    missing = tuple(s for s in spans if s.lower() not in blob)
    return FaithfulnessResult(
        passed=not missing,
        missing=missing,
        evidence_chars=len(blob),
    )
