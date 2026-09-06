"""Plugin trust store (M25): enable + capability flags per pack.

Trust file: ``workspace/plugins/.trust.yaml``

Simplification: local YAML only — not signed marketplace receipts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

TRUST_FILENAME = ".trust.yaml"


@dataclass
class TrustEntry:
    enabled: bool = True
    allow_shell_hooks: bool = False
    allow_mcp: bool = False


@dataclass
class TrustStore:
    packs: dict[str, TrustEntry] = field(default_factory=dict)
    path: Path | None = None

    def get(self, pack_id: str) -> TrustEntry | None:
        return self.packs.get(pack_id)

    def is_enabled(self, pack_id: str) -> bool:
        entry = self.packs.get(pack_id)
        return bool(entry and entry.enabled)

    def allows_mcp(self, pack_id: str) -> bool:
        entry = self.packs.get(pack_id)
        return bool(entry and entry.enabled and entry.allow_mcp)

    def allows_shell_hooks(self, pack_id: str) -> bool:
        entry = self.packs.get(pack_id)
        return bool(entry and entry.enabled and entry.allow_shell_hooks)


def trust_path(workspace_root: Path) -> Path:
    return workspace_root.expanduser().resolve() / "plugins" / TRUST_FILENAME


def load_trust_store(workspace_root: Path) -> TrustStore:
    path = trust_path(workspace_root)
    if not path.is_file():
        return TrustStore(path=path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Trust file must be a mapping: {path}")
    raw_packs = data.get("packs") or {}
    if not isinstance(raw_packs, dict):
        raise ValueError(f"trust.packs must be a mapping: {path}")
    packs: dict[str, TrustEntry] = {}
    for pid, spec in raw_packs.items():
        if not isinstance(spec, dict):
            raise ValueError(f"trust.packs.{pid} must be a mapping")
        packs[str(pid)] = TrustEntry(
            enabled=bool(spec.get("enabled", False)),
            allow_shell_hooks=bool(spec.get("allow_shell_hooks", False)),
            allow_mcp=bool(spec.get("allow_mcp", False)),
        )
    return TrustStore(packs=packs, path=path)


def save_trust_store(store: TrustStore, workspace_root: Path) -> Path:
    path = trust_path(workspace_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "packs": {
            pid: {
                "enabled": entry.enabled,
                "allow_shell_hooks": entry.allow_shell_hooks,
                "allow_mcp": entry.allow_mcp,
            }
            for pid, entry in sorted(store.packs.items())
        }
    }
    path.write_text(
        "# Plugin trust (M25). Install ≠ enable. Shell/MCP need explicit flags.\n"
        + yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    store.path = path
    return path


def default_trust_for_pack(
    *,
    has_mcp: bool,
    has_shell_hooks: bool,
    enabled: bool = True,
) -> TrustEntry:
    """Sensible defaults when synthesizing trust for seeded packs."""
    return TrustEntry(
        enabled=enabled,
        allow_shell_hooks=has_shell_hooks,
        allow_mcp=has_mcp,
    )


def pack_has_shell_hooks(hooks: dict[str, list[Any]]) -> bool:
    for items in hooks.values():
        for item in items:
            if isinstance(item, dict) and str(item.get("type") or "") in (
                "script",
                "shell",
            ):
                return True
    return False


def ensure_trust_entries(
    store: TrustStore,
    *,
    pack_summaries: dict[str, tuple[bool, bool]],
    write: bool = False,
    workspace_root: Path | None = None,
) -> TrustStore:
    """Fill missing trust entries from pack capability summaries.

    ``pack_summaries`` maps pack_id → (has_mcp, has_shell_hooks).
    """
    changed = False
    for pid, (has_mcp, has_shell) in pack_summaries.items():
        if pid in store.packs:
            continue
        store.packs[pid] = default_trust_for_pack(
            has_mcp=has_mcp, has_shell_hooks=has_shell, enabled=True
        )
        changed = True
        logger.info(
            "Synthesized trust for pack %s (enabled, mcp=%s, shell=%s)",
            pid,
            has_mcp,
            has_shell,
        )
    if write and changed and workspace_root is not None:
        save_trust_store(store, workspace_root)
    return store


def set_trust(
    store: TrustStore,
    pack_id: str,
    *,
    enabled: bool | None = None,
    allow_shell_hooks: bool | None = None,
    allow_mcp: bool | None = None,
) -> TrustEntry:
    entry = store.packs.get(pack_id) or TrustEntry(enabled=False)
    if enabled is not None:
        entry.enabled = enabled
    if allow_shell_hooks is not None:
        entry.allow_shell_hooks = allow_shell_hooks
    if allow_mcp is not None:
        entry.allow_mcp = allow_mcp
    store.packs[pack_id] = entry
    return entry
