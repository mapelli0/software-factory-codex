"""Remove the old account-wide Software Factory installation. Preview by default."""

import argparse
import codecs
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import tomllib
from pathlib import Path


ROLES = ("intake", "intake-conversation", "spec-writer", "builder", "approver",
         "reviewer-code", "reviewer-security", "reviewer-ui", "reviewer-ux")
BIN = ("job", "gate", "route", "dashboard.py", "projects.py", "migration.py", "runtime.py")
BUNDLE = ("config.json", "dashboard.html", "checks.ps1", "checks.sh", "legacy-files.json")


def default_data():
    if os.environ.get("SOFTWARE_FACTORY_HOME"):
        return Path(os.environ["SOFTWARE_FACTORY_HOME"])
    if os.name != "nt":
        return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "software-factory-codex"
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    for parent in local.parents:
        if parent.name.lower() == "packages" and any(
            name.lower().startswith("#!sandbox.") for name in local.relative_to(parent).parts
        ):
            local = parent.parent
            break
    return local / "software-factory-codex"


def checked(path):
    """Refuse redirected or noncanonical paths, including parent junctions."""
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError(f"expected an absolute path without links or parent traversals: {path}")
    return path


def read_file(path):
    checked(path)
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError(f"expected a regular file: {path}")
    return path.read_bytes()


def undo_permissions(original, data):
    """Match the installer's exact lines and verify the complete decoded TOML diff."""
    if original is None:
        return None
    encoding = "utf-8-sig" if original.startswith(codecs.BOM_UTF8) else "utf-8"
    content = original.decode(encoding)
    settings = tomllib.loads(content)
    folder = data.as_posix()
    expected = {"extends": ":workspace", "workspace_roots": {folder: True}}
    profiles = settings.get("permissions", {})
    profile = profiles.get("factory") if isinstance(profiles, dict) else None
    if profile != expected:
        if profile is not None or settings.get("default_permissions") == "factory":
            print("Kept customized factory permission settings. Review them in the Codex config.")
        return original
    remove = ['[permissions.factory]', 'extends = ":workspace"', '',
              '[permissions.factory.workspace_roots]', f'{json.dumps(folder, ensure_ascii=False)} = true']
    # The original installer always inserted one blank line immediately before these tables.
    section = r"^(?:\r?\n)?" + r"\r?\n".join(map(re.escape, remove)) + r"(?:\r?\n|$)"
    updated, count = re.subn(section, "", content, flags=re.MULTILINE)
    if count != 1:
        print("Kept customized factory permission settings. Review them in the Codex config.")
        return original
    if settings.get("default_permissions") == "factory":
        updated, count = re.subn(r'^default_permissions = "factory"(?:\r?\n|$)', "", updated, flags=re.MULTILINE)
        if count != 1:
            print("Kept customized default permissions. Review them in the Codex config.")
            return original
        del settings["default_permissions"]
    del profiles["factory"]
    if not profiles:
        del settings["permissions"]
    if tomllib.loads(updated) != settings:
        raise ValueError("could not preserve unrelated Codex settings")
    return updated.encode(encoding)


def replace_config(path, original, updated):
    """Publish atomically while retaining the original file's permissions."""
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".factory-uninstall-", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(updated)
    try:
        if read_file(path) != original:
            raise ValueError(f"changed during rollback, retry: {path}")
        if os.name == "nt":
            import ctypes
            if not ctypes.windll.kernel32.ReplaceFileW(str(path), str(temporary), None, 0, None, None):
                raise ctypes.WinError()
        else:
            temporary.chmod(stat.S_IMODE(path.stat().st_mode))
            temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def uninstall(codex, data, apply=False):
    codex = checked(codex.expanduser().absolute())
    data = checked(data.expanduser().absolute())
    if data.is_relative_to(codex) or codex.is_relative_to(data):
        raise ValueError("choose separate Codex and global factory data folders")
    receipt = data / "installation.json"
    raw_receipt = read_file(receipt)
    if raw_receipt is None:
        print(f"No global installation receipt at {receipt}.")
        return
    info = json.loads(raw_receipt)
    skill = codex / "skills/factory"
    files = info.get("files") if isinstance(info, dict) else None
    if not isinstance(files, dict) or not files or Path(info.get("runtime") or "") != skill:
        raise ValueError(f"receipt does not identify the selected Codex global installation: {receipt}")
    targets = {skill / name for name in ("factory.py", "SKILL.md", "LICENSE")}
    targets.update(skill / "factory" / name for name in BUNDLE)
    targets.update(skill / "factory/bin" / name for name in BIN)
    targets.update(codex / "agents" / f"factory-{name}.toml" for name in ROLES)
    contents = {}
    for name, digest in files.items():
        path = Path(name)
        if path not in targets or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError(f"unexpected entry in global installation receipt: {name}")
        content = read_file(path)
        if content is None:
            continue
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f"locally edited, save or move this file before uninstalling: {path}")
        contents[path] = content

    owners = list((data / "projects").glob("*/jobs/.owner"))
    if owners:
        raise ValueError(f"finish or release the active factory run first: {owners[0]}")
    board = read_file(data / "dashboard.json")
    if board and json.loads(board).get("token"):
        raise ValueError(f"stop the global dashboard first: python \"{skill / 'factory.py'}\" dashboard stop")

    config = codex / "config.toml"
    original = read_file(config)
    updated = undo_permissions(original, data)
    cache = checked(skill / "factory/bin/__pycache__")
    if cache.exists():
        for item in cache.iterdir():
            if re.fullmatch(r"(dashboard|migration|projects|runtime)\.[A-Za-z0-9_-]+(?:\.opt-[12])?\.pyc", item.name):
                contents[item] = read_file(item)
    for lock in (skill / ".permissions.lock", data / "install.lock"):
        value = read_file(lock)
        if value in (b"", b"0"):
            contents[lock] = value
    contents[receipt] = raw_receipt  # Last so interrupted removal can be retried.
    print(f"{'Applying rollback' if apply else 'Preview'} of global Software Factory in {codex}")
    if updated != original:
        print(f"Remove generated factory permission settings from {config}")
    for path in contents:
        print(f"Remove {path}")
    print(f"Project history and other data are preserved in {data}.")
    if not apply:
        return
    if updated != original:
        replace_config(config, original, updated)
    for path, expected in contents.items():
        if read_file(path) != expected:
            raise ValueError(f"changed during rollback, retry: {path}")
        path.unlink()
    for directory in (cache, skill / "factory/bin", skill / "factory", skill, data):
        if checked(directory).is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    print("Global rollback complete.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex"))
    parser.add_argument("--data-dir", type=Path, default=default_data(), help="old global data folder containing installation.json")
    parser.add_argument("--apply", action="store_true", help="apply the listed removals")
    args = parser.parse_args()
    try:
        uninstall(args.codex_home, args.data_dir, args.apply)
    except (OSError, ValueError) as error:
        parser.exit(1, f"uninstall: {error}\n")


if __name__ == "__main__":
    main()
