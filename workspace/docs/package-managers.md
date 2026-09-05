# Package managers

This project prefers **pnpm** for JavaScript workspaces when applicable.

Python packaging uses **uv** under `backend/` (`uv sync`, `uv run pytest`).

Do not mix npm and pnpm lockfiles in the same workspace without an explicit decision.
