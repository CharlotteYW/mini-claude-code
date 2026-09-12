"""M36 unit tests: hit@k, faithfulness, qrels loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_claude_code.eval.faithfulness import check_faithfulness
from mini_claude_code.eval.metrics import (
    cite_key,
    hit_at_k,
    mean_reciprocal_rank,
    path_only_hit_at_k,
)
from mini_claude_code.eval.retrieval import load_qrels

pytestmark = pytest.mark.unit


def test_cite_key_and_hit_at_k() -> None:
    assert cite_key("docs/a.md", 0) == "docs/a.md#0"
    ranked = ["docs/x.md#0", "docs/exact_token.md#0", "docs/y.md#1"]
    rel = ["docs/exact_token.md#0"]
    assert hit_at_k(ranked, rel, k=2) == 1.0
    assert hit_at_k(ranked, rel, k=1) == 0.0
    assert mean_reciprocal_rank(ranked, rel) == pytest.approx(0.5)
    assert path_only_hit_at_k(ranked, ["docs/exact_token.md"], k=2) == 1.0


def test_faithfulness_pass_and_fail() -> None:
    ok = check_faithfulness(
        "The marker is M36_MARKER_PURPLE_ORBIT",
        ["doc says M36_MARKER_PURPLE_ORBIT launched"],
        required_spans=["M36_MARKER_PURPLE_ORBIT"],
    )
    assert ok.passed
    bad = check_faithfulness(
        "The answer invents SECRET_HALLUCINATION",
        ["only boring evidence here"],
        required_spans=["SECRET_HALLUCINATION"],
    )
    assert not bad.passed
    assert "SECRET_HALLUCINATION" in bad.missing


def test_load_qrels_packaged() -> None:
    from mini_claude_code.eval.retrieval import default_qrels_path

    cases = load_qrels(default_qrels_path())
    ids = {c.id for c in cases}
    assert "keyword_exact_marker" in ids
    assert "hybrid_preferred_semantic" in ids
    kw = next(c for c in cases if c.id == "keyword_exact_marker")
    assert kw.mode == "keyword"
    assert "docs/exact_token.md#0" in kw.relevant


def test_load_qrels_rejects_empty(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("cases: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        load_qrels(path)
