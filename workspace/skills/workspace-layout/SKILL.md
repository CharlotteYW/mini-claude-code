---
name: workspace-layout
description: >
  How this mini-claude-code workspace is organized (AGENT.md, subagents, skills).
  Load when the user asks about project layout or where to put files.
---

# Workspace layout

- `AGENT.md` — durable project norms injected every turn (not chat history).
- `subagents/*.yaml` — child agent definitions for `run_subagent` (isolated context).
- `skills/<name>/SKILL.md` — progressive-disclosure playbooks (`load_skill`).
- Application code for the agent lives under the repo `backend/`, not necessarily in this workspace folder.

Prefer editing files under this workspace when the user asks for demos; keep secrets out of the workspace.
