"""Install or update the user-wide software factory from this checkout."""

import argparse
import codecs
import hashlib
import json
import os
import stat
import sys
import tempfile
import tomllib
from pathlib import Path
from uuid import uuid4

SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE / "factory/bin"))
from projects import DEFAULT_HOME, HOME, VERSION, read_json, write_json
from runtime import exclusive_lock


def read_config(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def configure_permissions(codex):
    """Add one workspace root when the user has no explicit permission configuration."""
    config = codex / "config.toml"
    override = os.environ.get("SOFTWARE_FACTORY_HOME")
    if (HOME == HOME.parent or (override and not Path(override).expanduser().is_absolute())
            or any(part.lower().startswith("#!sandbox.") for part in HOME.parts)
            or any(parent.is_relative_to(HOME) for parent in (Path.home(), DEFAULT_HOME.resolve(), codex))
            or HOME.is_relative_to(codex)):
        return "Skipped permission setup. Choose a dedicated, permanent, absolute SOFTWARE_FACTORY_HOME."
    if config.resolve() != config:
        return f"Kept the linked config at {config}. See INSTALL.md to configure its permissions."

    original = read_config(config)
    raw = original or b""
    saved = raw.decode("utf-8-sig")
    settings = tomllib.loads(saved)
    profiles = settings.get("permissions", {})
    profile = profiles.get("factory") if isinstance(profiles, dict) else None
    legacy = {"sandbox_mode", "sandbox_workspace_write"}.intersection(settings)
    if not legacy and settings.get("default_permissions") == "factory" and isinstance(profile, dict):
        roots = profile.get("workspace_roots", {})
        if (profile.get("extends") == ":workspace" and isinstance(roots, dict)
                and any(enabled is True and Path(key).expanduser() == HOME for key, enabled in roots.items())):
            return f"The factory permission profile already includes {HOME} in {config}."
    choices = legacy | {"default_permissions", "permissions"}.intersection(settings)
    if choices:
        return f"Kept your existing {', '.join(sorted(choices))} in {config}. See INSTALL.md for manual setup."

    newline = "\r\n" if b"\r\n" in raw else "\n"
    folder = HOME.as_posix()
    header = 'default_permissions = "factory"' + newline
    section = newline.join(("[permissions.factory]", 'extends = ":workspace"', "",
                            "[permissions.factory.workspace_roots]", f"{json.dumps(folder, ensure_ascii=False)} = true", ""))
    updated = header + saved + (newline if saved and not saved.endswith("\n") else "") + newline + section
    expected = {**settings, "default_permissions": "factory",
                "permissions": {"factory": {"extends": ":workspace", "workspace_roots": {folder: True}}}}
    if tomllib.loads(updated) != expected:
        raise ValueError("could not preserve existing Codex settings")
    encoding = "utf-8-sig" if raw.startswith(codecs.BOM_UTF8) else "utf-8"
    with tempfile.NamedTemporaryFile(dir=codex, prefix=".factory-config-", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        temporary.write_bytes(updated.encode(encoding))
        if read_config(config) != original:
            raise ValueError("Codex settings changed during installation. Run the installer again.")
        if original is None:
            # Publish without replacing a config concurrently created by another process.
            if os.name == "nt":
                temporary.rename(config)
            else:
                os.link(temporary, config)
        elif os.name == "nt":
            # Preserve the existing Windows file's ACL when replacing its contents.
            import ctypes
            if not ctypes.windll.kernel32.ReplaceFileW(str(config), str(temporary), None, 0, None, None):
                raise ctypes.WinError()
        else:
            temporary.chmod(stat.S_IMODE(config.stat().st_mode))
            temporary.replace(config)
    finally:
        temporary.unlink(missing_ok=True)
    return (f"Set the user default permission profile to 'factory' in {config}. It adds write access to {HOME}.\n"
            "In a fresh project chat, select Custom (config.toml) in the permissions control if needed.")


def install(skill, agents):
    for directory in (SOURCE, skill, agents):
        if HOME.is_relative_to(directory) or directory.is_relative_to(HOME):
            raise ValueError("choose a factory data directory separate from the source, skill and agents")
    targets = {skill / "SKILL.md": SOURCE / ".agents/skills/factory/SKILL.md",
               skill / "factory.py": SOURCE / "factory.py", skill / "LICENSE": SOURCE / "LICENSE"}
    for name in ["config.json", "dashboard.html", "checks.ps1", "checks.sh", "legacy-files.json"]:
        targets[skill / "factory" / name] = SOURCE / "factory" / name
    for name in ("job", "gate", "route", "dashboard.py", "projects.py", "migration.py", "runtime.py"):
        targets[skill / "factory/bin" / name] = SOURCE / "factory/bin" / name
    for name in ("intake", "intake-conversation", "spec-writer", "builder", "approver",
                 "reviewer-code", "reviewer-security", "reviewer-ui", "reviewer-ux"):
        targets[agents / f"factory-{name}.toml"] = SOURCE / ".codex/agents" / f"{name}.toml"
    manifest = HOME / "installation.json"
    with exclusive_lock(HOME / "install.lock"):
        previous = read_json(manifest, {})
        pending = {}
        hashes = {}
        for dest, source in targets.items():
            if dest.resolve() != dest or dest.is_relative_to(SOURCE):
                raise ValueError(f"choose separate user installation folders: {dest}")
            content = source.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            hashes[str(dest)] = digest
            if dest.exists():
                current = hashlib.sha256(dest.read_bytes()).hexdigest()
                if current == digest:
                    continue
                if current != previous.get("files", {}).get(str(dest)):
                    raise ValueError(f"preserve the existing or locally edited file before updating: {dest}")
            pending[dest] = content
        # Validate every destination first. Each file replacement is atomic and retryable.
        for dest, content in pending.items():
            dest.parent.mkdir(parents=True, exist_ok=True)
            temporary = dest.with_name(f".{dest.name}.{uuid4().hex}.tmp")
            temporary.write_bytes(content)
            temporary.replace(dest)
        write_json(manifest, {"version": VERSION, "source": str(SOURCE), "runtime": str(skill), "files": hashes})
    print(f"Software Factory {VERSION}\nLauncher: {skill / 'factory.py'}\nAgents: {agents}\nLocal data: {HOME}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", nargs="*", type=Path, help="inventory registered checkouts and these folders")
    parser.add_argument("--skip-permissions", action="store_true", help="leave Codex permission settings as they are")
    args = parser.parse_args()
    codex = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().resolve()
    skill = codex / "skills/factory"
    agents = codex / "agents"
    install(skill.absolute(), agents.absolute())
    if args.skip_permissions:
        print("Skipped Codex permission setup (--skip-permissions).")
    else:
        try:
            with exclusive_lock(skill / ".permissions.lock"):
                print(configure_permissions(codex))
        except (OSError, ValueError) as error:
            print(f"Factory installed. Permission setup needs attention: {error}. See INSTALL.md.", file=sys.stderr)
    if args.scan is not None:
        from migration import discover
        return discover(["--remember", *map(str, args.scan)])
    print("Open an application in Codex. Use $factory cleanup to check it or $factory to start.")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as error:
        sys.exit(f"install: {error}")
