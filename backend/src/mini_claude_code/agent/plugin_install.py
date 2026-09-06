"""Plugin install helpers (M25): copy path or git clone into workspace/plugins."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

from mini_claude_code.agent.plugin_trust import (
    TrustEntry,
    load_trust_store,
    save_trust_store,
    set_trust,
)
from mini_claude_code.agent.plugins import PLUGIN_MANIFEST, load_plugin_manifest

logger = logging.getLogger(__name__)

_GIT_URL_RE = re.compile(r"^(https?://|git@|ssh://).+", re.IGNORECASE)


def is_git_source(source: str) -> bool:
    s = source.strip()
    if s.endswith(".git"):
        return True
    return bool(_GIT_URL_RE.match(s))


def parse_version(raw: str) -> tuple[int, int, int]:
    text = raw.strip().lstrip("v")
    parts = text.split(".")
    nums: list[int] = []
    for p in parts[:3]:
        m = re.match(r"^(\d+)", p)
        if not m:
            raise ValueError(f"Invalid version segment in {raw!r}")
        nums.append(int(m.group(1)))
    while len(nums) < 3:
        nums.append(0)
    return nums[0], nums[1], nums[2]


def check_requires(
    requires: dict[str, str],
    *,
    package_version: str,
) -> None:
    """Validate teaching ``requires`` map. Supports ``mini_claude_code: '>=x.y.z'``."""
    if not requires:
        return
    raw = requires.get("mini_claude_code")
    if raw is None:
        return
    spec = str(raw).strip()
    if spec.startswith(">="):
        need = parse_version(spec[2:].strip())
        have = parse_version(package_version)
        if have < need:
            raise ValueError(
                f"Plugin requires mini_claude_code>={need[0]}.{need[1]}.{need[2]}, "
                f"have {package_version}"
            )
        return
    raise ValueError(
        f"Unsupported requires.mini_claude_code spec {spec!r} "
        "(teaching simplification: only '>=x.y.z')"
    )


def install_plugin_from_path(
    source: Path,
    *,
    workspace_root: Path,
    force: bool = False,
    pack_id: str | None = None,
    package_version: str = "0.1.0",
) -> Path:
    """Copy a plugin directory into ``workspace/plugins/<id>/``."""
    src = source.expanduser().resolve()
    if not src.is_dir():
        raise ValueError(f"Install source is not a directory: {src}")
    manifest = src / PLUGIN_MANIFEST
    if not manifest.is_file():
        raise ValueError(f"No {PLUGIN_MANIFEST} in {src}")
    pack = load_plugin_manifest(manifest)
    check_requires(pack.requires, package_version=package_version)
    dest_id = pack_id or pack.id or src.name
    dest = workspace_root.expanduser().resolve() / "plugins" / dest_id
    if dest.exists():
        if not force:
            raise ValueError(
                f"Plugin already installed at {dest} (pass force=True to replace)"
            )
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    # Re-load from dest so paths normalize under workspace
    installed = load_plugin_manifest(dest / PLUGIN_MANIFEST)
    check_requires(installed.requires, package_version=package_version)
    _register_trust_disabled(workspace_root, dest_id)
    logger.info("Installed plugin %s from path → %s", dest_id, dest)
    return dest


def install_plugin_from_git(
    url: str,
    *,
    workspace_root: Path,
    force: bool = False,
    pack_id: str | None = None,
    package_version: str = "0.1.0",
) -> Path:
    """Clone a git URL into a temp dir under plugins, then normalize to pack id."""
    import tempfile

    root = workspace_root.expanduser().resolve() / "plugins"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mcc-plugin-") as tmp:
        tmp_path = Path(tmp) / "clone"
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", url, str(tmp_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ValueError("git not found on PATH") from exc
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"git clone failed: {exc.stderr or exc}") from exc
        # Pack may be repo root or a nested folder with plugin.yaml
        manifest = tmp_path / PLUGIN_MANIFEST
        if not manifest.is_file():
            candidates = list(tmp_path.glob(f"*/{PLUGIN_MANIFEST}"))
            if len(candidates) == 1:
                tmp_path = candidates[0].parent
                manifest = candidates[0]
            else:
                raise ValueError(
                    f"No {PLUGIN_MANIFEST} at repo root "
                    f"(found {len(candidates)} nested)"
                )
        return install_plugin_from_path(
            tmp_path,
            workspace_root=workspace_root,
            force=force,
            pack_id=pack_id,
            package_version=package_version,
        )


def _register_trust_disabled(workspace_root: Path, pack_id: str) -> None:
    store = load_trust_store(workspace_root)
    set_trust(
        store,
        pack_id,
        enabled=False,
        allow_shell_hooks=False,
        allow_mcp=False,
    )
    # Keep existing entry flags if re-install with force? Plan: disabled fresh.
    store.packs[pack_id] = TrustEntry(
        enabled=False, allow_shell_hooks=False, allow_mcp=False
    )
    save_trust_store(store, workspace_root)
