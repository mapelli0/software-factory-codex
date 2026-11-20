"""Install or update the user-wide software factory from this checkout."""

import argparse
import hashlib
import os
import sys
from pathlib import Path
from uuid import uuid4

SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE / "factory/bin"))
from projects import HOME, VERSION, read_json, write_json
from runtime import exclusive_lock


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
    args = parser.parse_args()
    codex = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().resolve()
    skill = codex / "skills/factory"
    agents = codex / "agents"
    install(skill.absolute(), agents.absolute())
    if args.scan is not None:
        from migration import discover
        return discover(["--remember", *map(str, args.scan)])
    print("Open an application in Codex. Use $factory cleanup to check it or $factory to start.")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as error:
        sys.exit(f"install: {error}")
