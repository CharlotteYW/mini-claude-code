"""Retrieval quality metrics (M36) — hit@k / MRR on cite keys."""

from __future__ import annotations

from collections.abc import Sequence


def cite_key(source_path: str, chunk_index: int) -> str:
    """Stable cite used across tools/evals: ``source_path#chunk_index``."""
    path = str(source_path).replace("\\", "/").lstrip("./")
    return f"{path}#{int(chunk_index)}"


def normalize_cite(cite: str) -> str:
    raw = cite.strip().replace("\\", "/")
    if "#" not in raw:
        return raw.lstrip("./")
    path, _, idx = raw.rpartition("#")
    return cite_key(path, int(idx))


def hit_at_k(
    ranked_cites: Sequence[str],
    relevant: Sequence[str] | set[str],
    *,
    k: int,
) -> float:
    """1.0 if any relevant cite appears in the top-k ranked list, else 0.0."""
    if k <= 0:
        raise ValueError("k must be positive")
    rel = {normalize_cite(c) for c in relevant}
    top = [normalize_cite(c) for c in list(ranked_cites)[:k]]
    return 1.0 if any(c in rel for c in top) else 0.0


def mean_reciprocal_rank(
    ranked_cites: Sequence[str],
    relevant: Sequence[str] | set[str],
) -> float:
    """MRR for one query: 1/rank of first relevant hit (0 if none)."""
    rel = {normalize_cite(c) for c in relevant}
    for i, cite in enumerate(ranked_cites, start=1):
        if normalize_cite(cite) in rel:
            return 1.0 / float(i)
    return 0.0


def path_only_hit_at_k(
    ranked_cites: Sequence[str],
    relevant_paths: Sequence[str] | set[str],
    *,
    k: int,
) -> float:
    """hit@k matching on ``source_path`` only (ignore chunk_index)."""
    if k <= 0:
        raise ValueError("k must be positive")
    rel = {str(p).replace("\\", "/").lstrip("./") for p in relevant_paths}
    for cite in list(ranked_cites)[:k]:
        path = normalize_cite(cite).rsplit("#", 1)[0]
        if path in rel:
            return 1.0
    return 0.0
