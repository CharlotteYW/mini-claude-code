"""Eval harness (M17 agent cases + M36 retrieval quality).

Runs outside the LangGraph topology: YAML agent cases with fake LLMs, and
optional golden-corpus retrieval hit@k (``mcc-eval --retrieval``).
"""

from __future__ import annotations
