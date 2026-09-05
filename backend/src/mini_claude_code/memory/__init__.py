"""Memory package — durable stores outside the chat transcript (M8/M20)."""

from mini_claude_code.memory.ingest import TextChunk, chunk_text, clean_text
from mini_claude_code.memory.neo4j_facts import (
    MemoryFact,
    format_facts_for_prompt,
    recall_facts,
    recall_facts_block,
    remember_fact,
)
from mini_claude_code.memory.pgvector_chunks import MemoryChunkHit, search_chunks
from mini_claude_code.memory.pgvector_notes import (
    MemoryNote,
    recall_notes,
    remember_note,
)
from mini_claude_code.memory.pipeline import IngestResult, ingest_paths

__all__ = [
    "IngestResult",
    "MemoryChunkHit",
    "MemoryFact",
    "MemoryNote",
    "TextChunk",
    "chunk_text",
    "clean_text",
    "format_facts_for_prompt",
    "ingest_paths",
    "recall_facts",
    "recall_facts_block",
    "recall_notes",
    "remember_fact",
    "remember_note",
    "search_chunks",
]
