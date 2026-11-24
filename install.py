#!/usr/bin/env python3
"""Install Software Factory in an application's .factory directory."""

import argparse
import hashlib
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
from project_skill import ENTRY_FILES, SKILL_DIR


MARKER = {"product": "software-factory-codex", "layout": "project-local-v1"}
WORKFLOW = ".agents/skills/factory/SKILL.md"
# The unmodified workflow shipped by the first project-local installer.
PRE_MODEL_WORKFLOW = "5916fec498b248abe2d8404a7af0e0432db756682110f9e106e669c5057052a1"
PRE_MODEL_REVIEWERS = {
    "routing": {risk: {"code": "default"} for risk in ("low", "medium", "high")},
    "surface_reviewers": {"ui": {"ux": "default", "ui": "default"}, "security": {"security": "default"}},
}
ROLES = ("approver", "builder", "intake", "intake-conversation", "spec-writer",
         "reviewer-code", "reviewer-security", "reviewer-ui", "reviewer-ux")
FILES = (
    "AGENTS.md", "INSTALL.md", "LICENSE", WORKFLOW,
    ".codex/config.toml", *(f".codex/agents/{role}.toml" for role in ROLES),
    "factory/checks.ps1", "factory/checks.sh", "factory/config.json", "factory/dashboard.html",
    "factory/bin/job", "factory/bin/gate", "factory/bin/route", "factory/bin/models",
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


def validate_skill_entry(project):
    directory = project
    for part in SKILL_DIR.parts:
        directory = directory / part
        check_destination(directory)
        if directory.exists() and not directory.is_dir():
            raise ValueError(f"expected a skill directory at {directory}")

    recognized = False
    for name, expected in ENTRY_FILES.items():
        path = directory / name
        check_destination(path)
        if path.exists():
            if not path.is_file() or path.read_bytes().replace(b"\r\n", b"\n") != expected.encode("utf-8"):
                raise ValueError(f"existing project skill entry at {path}; move or rename it to install $factory")
            recognized = True
    if not recognized and directory.exists() and any(directory.iterdir()):
        raise ValueError(f"existing project skill at {directory}; move or rename it to install $factory")


def upgrade_contents(name, installed, bundled):
    """Update the old stock workflow and add model settings without replacing project settings."""
    if name == WORKFLOW:
        contents = installed.read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(contents).hexdigest() == PRE_MODEL_WORKFLOW:
            return bundled
        if contents != bundled.read_bytes().replace(b"\r\n", b"\n"):
            print(f"Kept customized workflow at {installed}. See the source workflow for model dispatch changes.")
    if name != "factory/config.json":
        return None
    try:
        config = json.loads(installed.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if not isinstance(config, dict) or "agent_models" in config or not PRE_MODEL_REVIEWERS.keys() <= config.keys():
        return None
    defaults = json.loads(bundled.read_text(encoding="utf-8"))
    config["agent_models"] = defaults["agent_models"]
    for key, old_defaults in PRE_MODEL_REVIEWERS.items():
        if config[key] == old_defaults:
            config[key] = defaults[key]
    return (json.dumps(config, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def install(checkout):
    project = validate_checkout(checkout)
    root = project / ".factory"
    files = {name: SOURCE / name for name in FILES}
    for name in ("checks.ps1", "config.json"):
        template = SOURCE / "factory" / "defaults" / name
        if template.is_file():
            files["factory/" + name] = template
    for source in files.values():
        if not source.is_file():
            raise ValueError(f"factory distribution is missing {source}")

    validate_skill_entry(project)
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
        validate_skill_entry(project)
        for name in (".gitignore", *files):
            path = root
            for part in Path(name).parts:
                path = path / part
                check_destination(path)
            if path.exists() and not path.is_file():
                raise ValueError(f"expected a regular file at {path}")

        destinations = {root / ".gitignore": b"*\n"}
        destinations.update({root / name: source for name, source in files.items()})
        # Publish the picker entry only after its full workflow is ready.
        destinations.update({project / SKILL_DIR / name: content.encode("utf-8")
                             for name, content in ENTRY_FILES.items()})
        for destination, source in destinations.items():
            if destination.is_file():
                if isinstance(source, bytes):
                    continue
                source = upgrade_contents(destination.relative_to(root).as_posix(), destination, source)
                if source is None:
                    continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(dir=destination.parent, prefix=".install-")
            os.close(fd)
            temp = Path(temp_name)
            try:
                if isinstance(source, bytes):
                    temp.write_bytes(source)
                else:
                    shutil.copy2(source, temp)
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
    print("Open Codex in the application root and type $factory status.")


if __name__ == "__main__":
    main()
