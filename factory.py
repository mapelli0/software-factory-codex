"""Run the global Software Factory from any application checkout."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
BIN = ROOT / "factory" / "bin"
sys.path.insert(0, str(BIN))

from projects import HOME, VERSION, checkout_root, git, project_dir, register


def doctor(root, args):
    """Test the current process's file access before registering or claiming work."""
    if len(args) > 1 or (args and not re.fullmatch(r"[0-9]{3,}-[a-z0-9-]+", args[0])):
        raise ValueError("usage: doctor [job-id]")
    print(f"Factory {VERSION} at {ROOT}\nProject: {root}\nFactory data: {HOME}", flush=True)
    marker = git(root, "config", "--local", "--get", "softwarefactory.projectid", check=False)
    if marker.returncode not in (0, 1):
        raise ValueError("could not read the factory project ID from Git")
    folders = [HOME]
    if marker.returncode == 0:
        jobs = project_dir(marker.stdout.decode().strip()) / "jobs"
        if args:
            folders.append(jobs / args[0])
        else:
            # A new checkout can have a marker before its first job directory exists.
            nearest = jobs
            while nearest != HOME and not nearest.exists():
                nearest = nearest.parent
            if nearest != HOME:
                folders.append(nearest)
    elif args:
        raise ValueError("this checkout has no registered job folder yet")
    for folder in folders:
        if folder.resolve() != folder:
            raise ValueError(f"expected a factory folder at {folder}, found a redirected path")
        probe = folder / f".factory-access-{uuid4().hex}"
        try:
            handle = probe.open("xb")
            try:
                with handle:
                    handle.write(b"ok")
            finally:
                probe.unlink()
        except FileNotFoundError as error:
            raise ValueError(f"folder not found: {folder}. Check the installation's Local data path and job ID.") from error
        except PermissionError as error:
            raise ValueError(f"write denied in {folder}. Check the active chat's writable folders against {HOME}. "
                             "Select the configured factory profile or add this data folder to the workspace, "
                             "then repeat the check with ordinary permissions.") from error
        print(f"Write check passed: {folder}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="application checkout or a subfolder")
    parser.add_argument("command", choices=("status", "register", "doctor", "job", "route", "gate", "dashboard", "cleanup", "discover"))
    parser.add_argument("args", nargs=argparse.REMAINDER)
    options = parser.parse_args()
    cmd, args = options.command, options.args
    if cmd == "discover":
        from migration import discover
        return discover(args)
    if cmd == "dashboard":
        return subprocess.call([sys.executable, str(BIN / "dashboard.py"), *args])
    root = checkout_root(options.project)
    if cmd == "doctor":
        return doctor(root, args)
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
