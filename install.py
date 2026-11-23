#!/usr/bin/env python3
"""Install Software Factory in an application's .factory directory."""

import argparse
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

# Import the checkout validator without leaving a cache in the source distribution.
SOURCE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(SOURCE / "factory" / "bin"))
from runtime import exclusive_lock, validate_checkout


MARKER = {"product": "software-factory-codex", "layout": "project-local-v1"}
ROLES = ("approver", "builder", "intake", "intake-conversation", "spec-writer",
         "reviewer-code", "reviewer-security", "reviewer-ui", "reviewer-ux")
FILES = (
    "AGENTS.md", "INSTALL.md", "LICENSE", ".agents/skills/factory/SKILL.md",
    ".codex/config.toml", *(f".codex/agents/{role}.toml" for role in ROLES),
    "factory/checks.ps1", "factory/checks.sh", "factory/config.json", "factory/dashboard.html",
    "factory/bin/job", "factory/bin/gate", "factory/bin/route",
    "factory/bin/runtime.py", "factory/bin/dashboard.py",
)


def check_destination(path):
    """Reject symlinks, including broken links, and Windows reparse points."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError(f"installation path contains a link: {path}")


def install(checkout):
    root = validate_checkout(checkout) / ".factory"
    files = {name: SOURCE / name for name in FILES}
    for name in ("checks.ps1", "config.json"):
        template = SOURCE / "factory" / "defaults" / name
        if template.is_file():
            files["factory/" + name] = template
    for source in files.values():
        if not source.is_file():
            raise ValueError(f"factory distribution is missing {source}")

    check_destination(root)
    marker = root / "installation.json"
    try:
        root.mkdir()
    except FileExistsError:
        check_destination(marker)
        if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")) != MARKER:
            raise ValueError(f"{root} already exists without a project-local factory marker; inspect it before installation")
    else:
        marker.write_text(json.dumps(MARKER, indent=2) + "\n", encoding="utf-8")

    lock = root / ".install.lock"
    check_destination(lock)
    with exclusive_lock(lock):
        for name in (".gitignore", *files):
            path = root
            for part in Path(name).parts:
                path = path / part
                check_destination(path)
            if path.exists() and not path.is_file():
                raise ValueError(f"expected a regular file at {path}")

        for name in (".gitignore", *files):
            destination = root / name
            if destination.is_file():
                continue  # Preserve installed checks, configuration and other local edits.
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(dir=destination.parent, prefix=".install-")
            os.close(fd)
            temp = Path(temp_name)
            try:
                if name == ".gitignore":
                    temp.write_bytes(b"*\n")
                else:
                    shutil.copy2(files[name], temp)
                temp.replace(destination)
            finally:
                temp.unlink(missing_ok=True)
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="root of an application Git checkout with a commit")
    args = parser.parse_args()
    try:
        root = install(args.project)
    except (OSError, ValueError) as error:
        parser.exit(1, f"install: {error}\n")
    print(f"Project factory: {root}")
    print("From the application root: python .factory/factory/bin/job project")


if __name__ == "__main__":
    main()
