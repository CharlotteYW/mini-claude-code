"""CLI for plugin install / list / trust (M25).

Usage:
  mcc-plugins install <path-or-git-url> [--force] [--id NAME]
  mcc-plugins list
  mcc-plugins trust <id> [--enable|--disable] [--allow-mcp] [--allow-shell-hooks]
  mcc-plugins disable <id>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mini_claude_code.agent.plugin_install import (
    install_plugin_from_git,
    install_plugin_from_path,
    is_git_source,
)
from mini_claude_code.agent.plugin_trust import (
    load_trust_store,
    pack_has_shell_hooks,
    save_trust_store,
    set_trust,
)
from mini_claude_code.agent.plugins import (
    discover_plugins,
    resolve_plugins,
)
from mini_claude_code.config import get_settings, resolve_workspace_root


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    repo_root = Path(__file__).resolve().parents[4]
    env_path = repo_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


def cmd_install(args: argparse.Namespace) -> int:
    settings = get_settings()
    ws = resolve_workspace_root(settings)
    source = args.source
    try:
        if is_git_source(source):
            dest = install_plugin_from_git(
                source,
                workspace_root=ws,
                force=args.force,
                pack_id=args.id,
            )
        else:
            dest = install_plugin_from_path(
                Path(source),
                workspace_root=ws,
                force=args.force,
                pack_id=args.id,
            )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Installed → {dest}")
    print("Trust: disabled (shell/MCP off). Enable with:")
    print(f"  mcc-plugins trust {dest.name} --enable [--allow-mcp] [--allow-shell-hooks]")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    settings = get_settings()
    ws = resolve_workspace_root(settings)
    # Discover without trust filter so list shows disabled packs too.
    packs = discover_plugins(ws, seed_examples=True)
    store = load_trust_store(ws)
    # Ensure synthesized entries exist for display
    from mini_claude_code.agent.plugin_trust import ensure_trust_entries

    ensure_trust_entries(
        store,
        pack_summaries={
            p.id: (bool(p.mcp), pack_has_shell_hooks(p.hooks)) for p in packs
        },
        write=True,
        workspace_root=ws,
    )
    store = load_trust_store(ws)
    if not packs:
        print("(no plugins under workspace/plugins/)")
        return 0
    print(f"workspace: {ws}")
    print(f"{'ID':<16} {'VER':<8} {'ON':<4} {'MCP':<4} {'SHELL':<6} NAME")
    for pack in packs:
        entry = store.get(pack.id)
        on = "yes" if entry and entry.enabled else "no"
        mcp = "yes" if entry and entry.allow_mcp else "no"
        shell = "yes" if entry and entry.allow_shell_hooks else "no"
        print(
            f"{pack.id:<16} {pack.version:<8} {on:<4} {mcp:<4} {shell:<6} {pack.name}"
        )
    active = resolve_plugins(settings, workspace_root=ws, seed_examples=False)
    print(f"\nActive (enabled) packs: {len(active)}")
    return 0


def cmd_trust(args: argparse.Namespace) -> int:
    settings = get_settings()
    ws = resolve_workspace_root(settings)
    store = load_trust_store(ws)
    packs = {p.id: p for p in discover_plugins(ws, seed_examples=True)}
    if args.pack_id not in packs and args.pack_id not in store.packs:
        print(f"ERROR: unknown pack {args.pack_id!r}", file=sys.stderr)
        return 1
    enabled = False if args.disable else True
    allow_mcp = None
    if args.allow_mcp:
        allow_mcp = True
    elif args.deny_mcp:
        allow_mcp = False
    allow_shell = None
    if args.allow_shell_hooks:
        allow_shell = True
    elif args.deny_shell_hooks:
        allow_shell = False
    set_trust(
        store,
        args.pack_id,
        enabled=enabled,
        allow_mcp=allow_mcp,
        allow_shell_hooks=allow_shell,
    )
    save_trust_store(store, ws)
    entry = store.get(args.pack_id)
    assert entry is not None
    print(
        f"trust {args.pack_id}: enabled={entry.enabled} "
        f"allow_mcp={entry.allow_mcp} allow_shell_hooks={entry.allow_shell_hooks}"
    )
    return 0


def cmd_disable(args: argparse.Namespace) -> int:
    settings = get_settings()
    ws = resolve_workspace_root(settings)
    store = load_trust_store(ws)
    set_trust(store, args.pack_id, enabled=False)
    save_trust_store(store, ws)
    print(f"disabled {args.pack_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mcc-plugins", description="Plugin install & trust (M25)")
    sub = p.add_subparsers(dest="command", required=True)

    inst = sub.add_parser("install", help="Install from local path or git URL")
    inst.add_argument("source", help="Directory path or git URL")
    inst.add_argument("--force", action="store_true", help="Replace existing pack dir")
    inst.add_argument("--id", dest="id", default=None, help="Override pack directory id")
    inst.set_defaults(func=cmd_install)

    lst = sub.add_parser("list", help="List installed packs and trust flags")
    lst.set_defaults(func=cmd_list)

    tr = sub.add_parser("trust", help="Enable/disable pack and set capabilities")
    tr.add_argument("pack_id")
    tr.add_argument("--enable", action="store_true", help="Enable pack (default)")
    tr.add_argument("--disable", action="store_true", help="Disable pack")
    tr.add_argument("--allow-mcp", action="store_true")
    tr.add_argument("--deny-mcp", action="store_true")
    tr.add_argument("--allow-shell-hooks", action="store_true")
    tr.add_argument("--deny-shell-hooks", action="store_true")
    tr.set_defaults(func=cmd_trust)

    dis = sub.add_parser("disable", help="Disable a pack")
    dis.add_argument("pack_id")
    dis.set_defaults(func=cmd_disable)

    return p


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    get_settings.cache_clear()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
