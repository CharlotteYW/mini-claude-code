"""Re-export the factory — keep import path stable as the llm package grows."""

from mini_claude_code.llm.factory import create_chat_model

__all__ = ["create_chat_model"]
