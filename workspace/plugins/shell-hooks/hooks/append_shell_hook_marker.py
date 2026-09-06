#!/usr/bin/env python3
"""M24 teaching Post hook: append a visible marker to string results."""

from __future__ import annotations

import json
import sys


def main() -> int:
    data = json.load(sys.stdin)
    result = data.get("result")
    if result is None:
        print("")
        return 0
    text = str(result)
    if "[hook:shell-hooks]" in text:
        print(json.dumps({"result": text}))
        return 0
    print(json.dumps({"result": f"{text}\n[hook:shell-hooks]"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
