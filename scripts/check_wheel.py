"""Fail if the built wheel is missing the MCP registry ownership marker."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

MARKER = "mcp-name: io.github.Dxfory/edgar-mcp"


def main() -> int:
    dist = Path("dist")
    wheels = sorted(dist.glob("*.whl"))
    if not wheels:
        print("no wheel in dist/", file=sys.stderr)
        return 1
    wheel = wheels[-1]
    with zipfile.ZipFile(wheel) as zf:
        metas = [name for name in zf.namelist() if name.endswith(".dist-info/METADATA")]
        if not metas:
            print(f"{wheel.name}: no METADATA", file=sys.stderr)
            return 1
        text = zf.read(metas[0]).decode("utf-8")
    if MARKER not in text:
        print(f"{wheel.name}: missing {MARKER}", file=sys.stderr)
        return 1
    print(f"ok {wheel.name} has {MARKER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
