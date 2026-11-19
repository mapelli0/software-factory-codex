"""Run the global Software Factory from any application checkout."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BIN = ROOT / "factory" / "bin"
sys.path.insert(0, str(BIN))

from projects import VERSION, checkout_root, register


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="application checkout or a subfolder")
    parser.add_argument("command", choices=("status", "register", "job", "route", "gate", "dashboard", "cleanup", "discover"))
    parser.add_argument("args", nargs=argparse.REMAINDER)
    options = parser.parse_args()
    cmd, args = options.command, options.args
    if cmd == "discover":
        from migration import discover
        return discover(args)
    if cmd == "dashboard":
        return subprocess.call([sys.executable, str(BIN / "dashboard.py"), *args])
    root = checkout_root(options.project)
    os.environ["SOFTWARE_FACTORY_PROJECT"] = str(root)
    if cmd == "cleanup":
        from migration import cleanup
        return cleanup(root, args)
    if cmd in {"status", "register"}:
        project_id, state, cfg = register(root)
        print(json.dumps({"project_id": project_id, "name": cfg.get("name", root.name),
                          "checkout": str(root), "jobs": str(state / "jobs"),
                          "notes": str(state / "PROJECT.local.md"), "concurrency": cfg["concurrency"],
                          "base_branch": cfg["base_branch"], "runtime": str(ROOT),
                          "version": VERSION}, ensure_ascii=False), flush=True)
        if cmd == "register":
            return 0
        cmd, args = "job", ["summary", *args]
    return subprocess.call([sys.executable, str(BIN / cmd), *args], cwd=root)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        sys.exit(f"factory: {error}")
