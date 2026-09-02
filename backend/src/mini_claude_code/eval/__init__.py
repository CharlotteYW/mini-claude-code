"""Eval harness for agent regression cases (M17).

Runs outside the LangGraph topology: load YAML cases, inject scripted fake LLMs,
invoke ``build_agent_graph``, assert on transcripts.
"""

from __future__ import annotations
