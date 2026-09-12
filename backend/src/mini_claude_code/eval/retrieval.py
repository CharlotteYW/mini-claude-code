"""Retrieval eval runner (M36): golden corpus + qrels → hit@k report."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from mini_claude_code.config import Settings, get_settings, repo_root
from mini_claude_code.eval.metrics import cite_key, hit_at_k, mean_reciprocal_rank
from mini_claude_code.memory.elasticsearch_chunks import search_keyword
from mini_claude_code.memory.hybrid import search_hybrid
from mini_claude_code.memory.pgvector_chunks import search_chunks
from mini_claude_code.memory.pgvector_notes import Embedder
from mini_claude_code.memory.pipeline import ingest_paths

RetrievalMode = Literal["keyword", "vector", "hybrid"]


def default_corpus_dir() -> Path:
    return (repo_root() / "backend" / "evals" / "corpus").resolve()


def default_qrels_path() -> Path:
    return (repo_root() / "backend" / "evals" / "qrels" / "rag_smoke.yaml").resolve()


@dataclass(frozen=True)
class QrelCase:
    id: str
    query: str
    mode: RetrievalMode
    k: int
    relevant: tuple[str, ...]  # cite keys source_path#index
    required_spans: tuple[str, ...] = ()


@dataclass
class RetrievalCaseResult:
    id: str
    mode: RetrievalMode
    passed: bool
    hit_at_k: float
    mrr: float
    ranked: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class RetrievalEvalReport:
    results: list[RetrievalCaseResult] = field(default_factory=list)
    ingest_summary: str = ""

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def format(self) -> str:
        lines = []
        if self.ingest_summary:
            lines.append(self.ingest_summary)
            lines.append("")
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(
                f"{status}  {r.id} mode={r.mode} "
                f"hit@k={r.hit_at_k:.0f} mrr={r.mrr:.3f}"
            )
            if r.ranked:
                lines.append(f"       ranked: {r.ranked[:5]}")
            if r.reason:
                lines.append(f"       {r.reason}")
        lines.append("")
        ok = len(self.results) - self.failed
        lines.append(f"{ok} passed, {self.failed} failed (retrieval)")
        return "\n".join(lines)


def load_qrels(path: Path) -> list[QrelCase]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"qrels must be a mapping: {path}")
    raw_cases = data.get("cases") or []
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"qrels.cases must be a non-empty list: {path}")
    out: list[QrelCase] = []
    for item in raw_cases:
        if not isinstance(item, dict):
            raise ValueError(f"qrel case must be a mapping: {path}")
        cid = str(item.get("id") or "").strip()
        query = str(item.get("query") or "").strip()
        mode = str(item.get("mode") or "keyword").strip().lower()
        k = int(item.get("k") or 3)
        if mode not in {"keyword", "vector", "hybrid"}:
            raise ValueError(f"unknown retrieval mode {mode!r} in {cid}")
        if not cid or not query:
            raise ValueError(f"qrel case needs id+query: {item!r}")
        rel_raw = item.get("relevant") or []
        if not isinstance(rel_raw, list) or not rel_raw:
            raise ValueError(f"qrel {cid}: relevant must be non-empty list")
        cites: list[str] = []
        for r in rel_raw:
            if isinstance(r, str):
                cites.append(r)
            elif isinstance(r, dict):
                cites.append(
                    cite_key(str(r["source_path"]), int(r.get("chunk_index", 0)))
                )
            else:
                raise ValueError(f"qrel {cid}: bad relevant entry {r!r}")
        spans = tuple(
            str(s).strip()
            for s in (item.get("required_spans") or [])
            if str(s).strip()
        )
        out.append(
            QrelCase(
                id=cid,
                query=query,
                mode=mode,  # type: ignore[arg-type]
                k=max(1, k),
                relevant=tuple(cites),
                required_spans=spans,
            )
        )
    return out


def _hits_to_cites(hits: Sequence[Any]) -> list[str]:
    return [cite_key(h.source_path, h.chunk_index) for h in hits]


def search_for_mode(
    mode: RetrievalMode,
    query: str,
    *,
    limit: int,
    settings: Settings,
    embedder: Embedder | None = None,
) -> list[Any]:
    if mode == "keyword":
        return list(search_keyword(query, limit=limit, settings=settings))
    if mode == "vector":
        return list(
            search_chunks(query, limit=limit, settings=settings, embedder=embedder)
        )
    if mode == "hybrid":
        return list(
            search_hybrid(
                query, limit=limit, settings=settings, embedder=embedder
            )
        )
    raise ValueError(f"unknown mode {mode!r}")


def stage_corpus(corpus_dir: Path, workspace: Path) -> Path:
    """Copy golden docs into ``workspace/docs`` (path-jail friendly)."""
    src = corpus_dir.expanduser().resolve()
    if not src.is_dir():
        raise FileNotFoundError(f"corpus dir missing: {src}")
    dest = (workspace / "docs").resolve()
    dest.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.glob("*")):
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
            (dest / path.name).write_text(
                path.read_text(encoding="utf-8"), encoding="utf-8"
            )
    return dest


def run_retrieval_eval(
    *,
    workspace: Path,
    corpus_dir: Path | None = None,
    qrels_path: Path | None = None,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    modes: Sequence[RetrievalMode] | None = None,
) -> RetrievalEvalReport:
    """Ingest golden corpus and score each qrel case."""
    settings = settings or get_settings()
    corpus_dir = corpus_dir or default_corpus_dir()
    qrels_path = qrels_path or default_qrels_path()
    cases = load_qrels(qrels_path)
    if modes:
        allow = set(modes)
        cases = [c for c in cases if c.mode in allow]

    docs = stage_corpus(corpus_dir, workspace)
    ingest = ingest_paths(
        "docs/*",
        workspace_root=workspace,
        settings=settings,
        embedder=embedder,
        write_pgvector=True,
        write_neo4j=True,
        write_elasticsearch=True,
    )
    report = RetrievalEvalReport(ingest_summary=ingest.summary())
    if ingest.errors:
        # Still attempt searches; failures will show in hit@k.
        pass

    for case in cases:
        try:
            hits = search_for_mode(
                case.mode,
                case.query,
                limit=max(case.k, 5),
                settings=settings,
                embedder=embedder,
            )
            ranked = _hits_to_cites(hits)
            score = hit_at_k(ranked, case.relevant, k=case.k)
            mrr = mean_reciprocal_rank(ranked, case.relevant)
            passed = score >= 1.0
            reason = "" if passed else f"expected one of {list(case.relevant)}"
            report.results.append(
                RetrievalCaseResult(
                    id=case.id,
                    mode=case.mode,
                    passed=passed,
                    hit_at_k=score,
                    mrr=mrr,
                    ranked=ranked,
                    reason=reason,
                )
            )
        except Exception as exc:  # noqa: BLE001 — surface as failed case
            report.results.append(
                RetrievalCaseResult(
                    id=case.id,
                    mode=case.mode,
                    passed=False,
                    hit_at_k=0.0,
                    mrr=0.0,
                    ranked=[],
                    reason=f"error: {exc}",
                )
            )
    # Keep docs path referenced for debugging
    _ = docs
    return report


def optional_soft_grade(
    invoke_structured: Callable[..., Any],
    llm: Any,
    *,
    question: str,
    answer: str,
    evidence: str,
) -> Any:
    """Optional M33 GradeResult judge (caller supplies invoke_structured + llm)."""
    from mini_claude_code.agent.structured import GradeResult

    prompt = (
        "Grade whether the answer is faithful to the evidence.\n"
        f"Question: {question}\n"
        f"Answer: {answer}\n"
        f"Evidence:\n{evidence}\n"
    )
    return invoke_structured(llm, GradeResult, prompt)
