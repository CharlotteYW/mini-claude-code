---
name: doc-research
description: >
  Playbook for researching docs in this workspace (plugin-bundled skill, M23).
  Load when answering questions that need structured reading of local markdown.
---

# Doc research playbook

1. Prefer `list_docs` / `read_doc` when the fake_docs MCP is available; otherwise use `read_file` / `grep_files`.
2. If a tool returns `CONTENT_POLICY_DENIED`, stop — do not invent withheld contents.
3. Cite paths or doc ids in the final answer.
4. Keep the answer short: summary, evidence bullets, open questions.
