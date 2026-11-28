#!/usr/bin/env python3
"""Install Software Factory in an application's .factory directory."""

import argparse
import hashlib
import json
import os
import re
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
WORKFLOW_RECEIPT = ".workflow-package.json"
# Install the helper before its callers. The hashes identify unmodified files
# from the four project-local releases that predate workflow receipts.
WORKFLOW_BASELINES = {
    "factory/bin/openspec_flow.py": set(),
    "factory/bin/job": {"09b8c4a08bc8257712a4be84c69336983e26cabb2a1506bc6383c71843964388"},
    WORKFLOW: {
        "5916fec498b248abe2d8404a7af0e0432db756682110f9e106e669c5057052a1",
        "ad42480f632cd68d89a8ff690e93f0386f57655f23e2b2a08770fb3610b99b67",
        "7e044c6f3b143a64b1194ccbb504574b67283082d94303f6afd4ded411680a51",
    },
}
PRE_MODEL_REVIEWERS = {
    "routing": {risk: {"code": "default"} for risk in ("low", "medium", "high")},
    "surface_reviewers": {"ui": {"ux": "default", "ui": "default"}, "security": {"security": "default"}},
}
ROLES = ("approver", "builder", "intake", "intake-conversation", "spec-writer",
         "reviewer-code", "reviewer-security", "reviewer-ui", "reviewer-ux")
FILES = (
    "AGENTS.md", "INSTALL.md", "LICENSE", *WORKFLOW_BASELINES,
    ".codex/config.toml", *(f".codex/agents/{role}.toml" for role in ROLES),
    "factory/checks.ps1", "factory/checks.sh", "factory/config.json", "factory/dashboard.html",
    "factory/bin/gate", "factory/bin/route", "factory/bin/models",
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


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def workflow_updates(root, files):
    """Plan the new helper, command and instructions together before replacing any file."""
    receipt = root / WORKFLOW_RECEIPT
    previous = {}
    if receipt.exists():
        try:
            previous = json.loads(receipt.read_text(encoding="utf-8"))
        except ValueError as error:
            raise ValueError(f"invalid workflow receipt at {receipt}: {error}") from error
        if (not isinstance(previous, dict) or set(previous) != set(WORKFLOW_BASELINES)
                or not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
                           for value in previous.values())):
            raise ValueError(f"unrecognized workflow receipt at {receipt}; inspect it before reinstalling")

    bundled = {}
    updates = {}
    conflicts = []
    for name, old_hashes in WORKFLOW_BASELINES.items():
        target = root / name
        bundled[name] = digest(files[name])
        if not target.exists():
            updates[target] = files[name]
            continue
        actual = digest(target)
        if actual == bundled[name]:
            continue
        if actual in old_hashes or actual == previous.get(name):
            updates[target] = files[name]
        elif previous.get(name) != bundled[name]:
            conflicts.append(str(target))
    if conflicts:
        raise ValueError("OpenSpec upgrade needs a manual merge. Back up and move the following "
                         "customized files aside, rerun the installer, then merge your edits "
                         "into the installed versions:\n  " + "\n  ".join(conflicts))
    if previous != bundled:
        updates[receipt] = (json.dumps(bundled, indent=2) + "\n").encode("utf-8")
    return updates


def upgrade_contents(name, installed, bundled):
    """Update stock files and add missing settings while preserving local choices."""
    if name == "factory/bin/models":
        installed_digest = digest(installed)
        if installed_digest == "85151792725e36779a4835e3ccb4c40e97acc2da8d9c47c5b43bdf28427a07c8":
            return bundled
        if installed_digest != digest(bundled):
            print(f"Kept customized file at {installed}. See {bundled} for the current model and reasoning settings.")
    if name != "factory/config.json":
        return None
    try:
        config = json.loads(installed.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if not isinstance(config, dict) or not PRE_MODEL_REVIEWERS.keys() <= config.keys():
        return None
    if {"agent_models", "reasoning_effort"} <= config.keys():
        return None
    defaults = json.loads(bundled.read_text(encoding="utf-8"))
    if "agent_models" not in config:
        config["agent_models"] = defaults["agent_models"]
        for key, old_defaults in PRE_MODEL_REVIEWERS.items():
            if config[key] == old_defaults:
                config[key] = defaults[key]
    config.setdefault("reasoning_effort", defaults["reasoning_effort"])
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
        for name in (".gitignore", WORKFLOW_RECEIPT, *files):
            path = root
            for part in Path(name).parts:
                path = path / part
                check_destination(path)
            if path.exists() and not path.is_file():
                raise ValueError(f"expected a regular file at {path}")

        destinations = workflow_updates(root, files)
        if not (root / ".gitignore").is_file():
            destinations[root / ".gitignore"] = b"*\n"
        for name, source in files.items():
            if name in WORKFLOW_BASELINES:
                continue
            destination = root / name
            if destination.is_file():
                source = upgrade_contents(name, destination, source)
            if source is not None:
                destinations[destination] = source
        # Publish the picker entry only after its full workflow is ready.
        for name, content in ENTRY_FILES.items():
            destination = project / SKILL_DIR / name
            if not destination.is_file():
                destinations[destination] = content.encode("utf-8")
        for destination, source in destinations.items():
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
