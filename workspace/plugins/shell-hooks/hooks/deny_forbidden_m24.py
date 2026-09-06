#!/usr/bin/env python3
"""M24 teaching Pre hook: deny run_shell when command contains FORBIDDEN_M24."""

from __future__ import annotations

import json
import sys


def main() -> int:
    data = json.load(sys.stdin)
    tool = data.get("tool")
    args = data.get("args") or {}
    command = str(args.get("command", ""))
    if tool == "run_shell" and "FORBIDDEN_M24" in command:
        print(
            json.dumps(
                {
                    "allow": False,
                    "reason": "shell-hooks pack blocked FORBIDDEN_M24 in run_shell",
                }
            )
        )
        return 0
    print(json.dumps({"allow": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
