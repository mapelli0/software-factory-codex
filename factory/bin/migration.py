"""Inventory and retire legacy factory files for one verified application."""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

from dashboard import request as dashboard_request
from projects import (FACTORY, HOME, checkout_root, config_for, git, read_json, register,
                      project_dir, registry, validation_policy, write_json)
from runtime import exclusive_lock, run_checks

BINDING = ".factory-project.local.json"
SKILL = ".agents/skills/factory/SKILL.md"
CORE = "factory/bin/job"
OWNER = "factory/jobs/.owner"
HISTORY = "factory/jobs"
MANIFEST = FACTORY / "legacy-files.json"
INVENTORY = HOME / "legacy.json"
JOB = re.compile(r"[0-9]{3,}-[a-z0-9-]+")
SHARED = {".gitignore", ".codex/config.toml", "AGENTS.md", "INSTALL.md"}
IGNORE = {".git", "node_modules", ".worktrees", "__pycache__", ".venv", "obj", ".vs"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe(root, relative):
    path = root / relative
    if not path.is_relative_to(root) or ".." in Path(relative).parts or path.resolve() != path:
        raise ValueError(f"linked or outside path requires review: {path}")
    return path


def protected_install(path):
    install = read_json(HOME / "installation.json", {})
    protected = {FACTORY.parent, HOME}
    protected.update(Path(install[k]) for k in ("source", "runtime") if k in install)
    return any(path.is_relative_to(p) for p in protected)


def candidate(path, *, partial=False):
    if (path / BINDING).is_file():
        return True
    if (path / SKILL).is_file() or ((path / CORE).is_file() and (path / "factory/config.json").is_file()):
        return True
    if partial:
        manifest = read_json(MANIFEST)
        for name, hashes in manifest.items():
            if not name.startswith((".codex/agents/", "factory/bin/")):
                continue
            source = safe(path, name)
            if source.is_file() and digest(source.read_bytes().replace(b"\r\n", b"\n")) in hashes:
                return True
    return False


def binding(path):
    if (path / BINDING).is_file():
        value = read_json(safe(path, BINDING)).get("checkout")
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError(f"invalid checkout in {path / BINDING}")
        return checkout_root(value)
    return checkout_root(path)


def discover(argv):
    parser = argparse.ArgumentParser(prog="factory discover")
    parser.add_argument("--remember", action="store_true")
    parser.add_argument("roots", nargs="*", type=Path)
    args = parser.parse_args(argv)
    found, errors = {}, []
    roots = {p.expanduser().resolve() for p in args.roots}
    roots.update(Path(record["checkout"]) for record in registry()["projects"].values())
    for supplied in sorted(roots):
        root = supplied.expanduser().resolve()
        print(f"Scanning {root}")
        if not root.is_dir():
            errors.append(f"unavailable: {root}")
            continue
        for parent, dirs, _ in os.walk(root, onerror=lambda err: errors.append(str(err))):
            path = Path(parent)
            dirs[:] = [d for d in dirs if d not in IGNORE and (path / d).resolve() == path / d]
            if protected_install(path):
                dirs.clear()
                continue
            if candidate(path):
                try:
                    app = binding(path)
                    if app != path and not (path / BINDING).exists():
                        raise ValueError("unbound nested copy; inspect manually")
                    found[str(path)] = str(app)
                    print(f"Found {path} -> {app}")
                except (ValueError, OSError) as error:
                    errors.append(f"{path}: {error}")
    if args.remember and found:
        with exclusive_lock(HOME / "legacy.lock"):
            write_json(INVENTORY, {**read_json(INVENTORY, {}), **found})
    for error in errors:
        print(f"Needs review: {error}", file=sys.stderr)
    return int(bool(errors))


def known_roots(app):
    roots = {app}
    roots.update(Path(path) for path, checkout in read_json(INVENTORY, {}).items() if Path(checkout) == app)
    return sorted(roots)


def ensure_ready(app, state):
    if (state / "migration.json").exists():
        raise ValueError("unfinished migration; run $factory cleanup")
    for path in known_roots(app):
        if not path.is_dir() and str(path) not in read_json(state / "retired.json", {}):
            raise ValueError(f"registered legacy location unavailable: {path}; review before running")
        if not protected_install(path) and candidate(path, partial=True):
            raise ValueError(f"legacy factory at {path}; run $factory cleanup before starting a global run")


def walk_files(root, relative):
    folder = safe(root, relative)
    if not folder.is_dir():
        return
    def failed(err):
        raise err
    for parent, dirs, files in os.walk(folder, onerror=failed):
        for name in dirs + files:
            safe(root, (Path(parent) / name).relative_to(root))
        for name in files:
            yield (Path(parent) / name).relative_to(root).as_posix()


def inspect(root, app):
    if protected_install(root):
        raise ValueError(f"protected source, global installation or backup: {root}")
    if not root.is_dir():
        raise ValueError(f"registered legacy location is unavailable: {root}")
    # Force an actual directory read so inaccessible folders cannot pass as clean.
    list(root.iterdir())
    if not candidate(root, partial=True):
        return None
    if binding(root) != app or (root != app and not (root / BINDING).is_file()):
        raise ValueError(f"unverified project binding: {root}")
    if not (safe(root, CORE).is_file() and safe(root, SKILL).is_file() and
            safe(root, ".codex/agents/builder.toml").is_file()):
        raise ValueError(f"incomplete or unrecognized factory files at {root}")
    if root == app and (root / "CODEX-MIGRATION-PLAN.md").exists() and (root / "LICENSE").exists():
        raise ValueError(f"possible factory source checkout: {root}")
    if (root / OWNER).exists():
        raise BlockingIOError(f"legacy run owns {root}; finish or recover it in the old factory")
    worktrees = safe(root, ".worktrees")
    registered = git(app, "worktree", "list", "--porcelain", "-z").stdout.split(b"\0")
    if (worktrees.is_dir() and any(worktrees.iterdir())) or any(
        Path(os.fsdecode(line[9:])).is_relative_to(worktrees) for line in registered if line.startswith(b"worktree ")
    ):
        raise BlockingIOError(f"finish or recover linked worktrees under {worktrees}")

    manifest = read_json(MANIFEST)
    files, history, kept = set(), [], []
    old_config = read_json(safe(root, "factory/config.json"))
    config_for(app)  # validate portable settings independently
    check_scripts = {}
    for platform in ("windows", "linux"):
        default = "checks.ps1" if platform == "windows" else "checks.sh"
        original = old_config.get("checks", {}).get(platform, {}).get("script", default)
        if not isinstance(original, str) or Path(original).is_absolute() or ".." in Path(original).parts:
            raise ValueError(f"review the legacy {platform} check script")
        src = (Path("factory") / original).as_posix()
        if safe(root, src).is_file():
            check_scripts[platform] = src
            files.add(src)
    for name, hashes in manifest.items():
        path = safe(root, name)
        if not path.is_file():
            continue
        match = digest(path.read_bytes().replace(b"\r\n", b"\n")) in hashes
        if match or name in {"factory/config.json", *check_scripts.values()}:
            files.add(name)
        elif name in SHARED:
            kept.append(name)
            if name == "AGENTS.md" and any(marker in path.read_text(encoding="utf-8-sig") for marker in ("factory/bin/job", "factory installation directory", ".factory-project.local.json")):
                raise ValueError(f"review legacy instructions mixed with project text in {path}")
        else:
            raise ValueError(f"locally edited factory file requires review: {path}")
    for name in (BINDING, "PROJECT.local.md", ".factory-dashboard.local.json", ".factory-dashboard.local.lock"):
        if safe(root, name).is_file():
            files.add(name)
    jobs_dir = safe(root, HISTORY)
    if jobs_dir.is_dir():
        for directory in jobs_dir.iterdir():
            if directory.name == ".lock":
                continue
            safe(root, directory.relative_to(root))
            if not JOB.fullmatch(directory.name) or not directory.is_dir():
                raise ValueError(f"unrecognized legacy job data: {directory}")
            job = read_json(safe(root, directory.relative_to(root) / "job.json"))
            if job.get("id") != directory.name:
                raise ValueError(f"legacy job identity mismatch: {directory}")
            if job.get("stage") not in {"merged", "rejected"}:
                raise BlockingIOError(f"finish job {directory.name} ({job.get('stage')}) in the old factory")
            if job.get("project_checkout") and Path(job["project_checkout"]).resolve() != app:
                raise ValueError(f"legacy job belongs to a different checkout: {directory}")
            history.append(directory.name)
            files.update(walk_files(root, directory.relative_to(root)))
    return {"root": str(root), "checkout": str(app), "files": {n: digest(safe(root, n).read_bytes()) for n in sorted(files)},
            "history": sorted(history), "checks": check_scripts, "kept_shared": kept}


def copy_verified(src, dst, expected):
    if dst.exists():
        if digest(dst.read_bytes()) != expected:
            raise ValueError(f"destination contains different data: {dst}")
        return
    data = src.read_bytes()
    if digest(data) != expected:
        raise ValueError(f"file changed since preview: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(uuid4().hex + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(dst)


def import_backup(plan, backup, state, project_id, app):
    cfg = read_json(backup / "factory/config.json")
    for platform, src in plan["checks"].items():
        name = "checks.ps1" if platform == "windows" else "checks.sh"
        copy_verified(backup / src, state / "checks" / name, plan["files"][src])
        cfg.setdefault("checks", {})[platform] = {"shell": "pwsh" if platform == "windows" else "bash", "script": name}
    settings = state / "settings.json"
    if settings.exists() and read_json(settings) != cfg:
        raise ValueError("existing project settings differ; review the two installations")
    write_json(settings, cfg)
    if "PROJECT.local.md" in plan["files"]:
        copy_verified(backup / "PROJECT.local.md", state / "PROJECT.local.md", plan["files"]["PROJECT.local.md"])
    for job_id in plan["history"]:
        prefix = f"{HISTORY}/{job_id}/"
        target = state / "jobs" / job_id
        job = read_json(backup / prefix / "job.json")
        job.update(project_id=project_id, project_checkout=str(app), worktree=str(state / "worktrees" / job_id))
        if (target / "job.json").exists() and read_json(target / "job.json") != job:
            raise ValueError(f"job ID collision while importing {job_id}")
        for rel, checksum in plan["files"].items():
            if rel.startswith(prefix) and rel != prefix + "job.json":
                copy_verified(backup / rel, target / rel.removeprefix(prefix), checksum)
        write_json(target / "job.json", job)
    revision = git(app, "rev-parse", "HEAD").stdout.decode().strip()
    policy = validation_policy(app, state, revision)
    check = run_checks(state / "policies", policy, app)
    if check.returncode:
        raise ValueError(f"project preflight failed; correct project checks and retry:\n{check.stdout}")


def verify_install():
    install = read_json(HOME / "installation.json", {})
    if Path(install.get("runtime", "")) != FACTORY.parent:
        raise ValueError("use the installed global launcher to apply cleanup")
    for file, checksum in install["files"].items():
        path = Path(file)
        if not path.is_file() or digest(path.read_bytes()) != checksum:
            raise ValueError(f"repair the global installation before retiring the local copy: {path}")


def apply_plan(plan, state, project_id, app):
    root = Path(plan["root"])
    backup = HOME / "backups" / project_id / plan["backup_id"]
    journal = state / "migration.json"
    if root != app and (root / BINDING).exists() and binding(root) != app:
        raise ValueError("legacy binding changed")
    with exclusive_lock(root / HISTORY / ".lock"):
        if (root / OWNER).exists():
            raise BlockingIOError("a legacy run is active")
        if not journal.exists():
            fresh = inspect(root, app)
            if fresh != {k: v for k, v in plan.items() if k != "backup_id"}:
                raise ValueError("legacy files changed; preview again")
            write_json(journal, plan)
        else:
            if any(safe(root, ".worktrees").glob("*")):
                raise BlockingIOError("a linked worktree appeared during migration")
            extras = set(walk_files(root, HISTORY)) - set(plan["files"]) - {HISTORY + "/.lock"}
            if extras:
                raise ValueError(f"new legacy job data requires review: {sorted(extras)[0]}")
        for rel, checksum in plan["files"].items():
            copy_verified(safe(root, rel), safe(backup, rel), checksum)
        write_json(backup / "migration-manifest.json", plan)
        import_backup(plan, backup, state, project_id, app)
        dashboard = read_json(root / ".factory-dashboard.local.json", {})
        if dashboard and dashboard_request(dashboard, "GET"):
            if not dashboard_request(dashboard, "POST"):
                raise ValueError("stop the old dashboard and retry")
            import time
            for _ in range(50):
                if not dashboard_request(dashboard, "GET"):
                    break
                time.sleep(0.1)
            else:
                raise ValueError("old dashboard is still responding")
        # Verify the entire deletion set before changing any original file.
        for rel, checksum in plan["files"].items():
            src = safe(root, rel)
            if src.exists() and digest(src.read_bytes()) != checksum:
                raise ValueError(f"file changed after backup: {src}")
        for rel in plan["files"]:
            safe(root, rel).unlink(missing_ok=True)
    (root / HISTORY / ".lock").unlink(missing_ok=True)
    parents = {p for rel in [*plan["files"], HISTORY + "/.lock"] for p in (root / rel).parents if p != root and p.is_relative_to(root)}
    for directory in sorted(parents, key=lambda p: len(p.parts), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    if candidate(root, partial=True):
        raise ValueError("legacy factory files are still present")
    register(app)
    write_json(state / "retired.json", {**read_json(state / "retired.json", {}), str(root): str(backup)})
    journal.unlink()
    print(f"Migrated: {app}\nBackup: {backup}\nReview tracked removals with git diff in {root}")


def cleanup(app, argv):
    parser = argparse.ArgumentParser(prog="factory cleanup")
    parser.add_argument("--apply", action="store_true", help="apply the reviewed migration")
    parser.add_argument("--expect", help="apply only if the preview ID still matches")
    parser.add_argument("--legacy", type=Path, help="include a separate legacy install bound to this checkout")
    args = parser.parse_args(argv)
    roots = known_roots(app)
    try:
        existing = next((k for k, r in registry()["projects"].items() if Path(r["checkout"]) == app), None)
        journal = project_dir(existing) / "migration.json" if existing else None
        print(f"Project: {app}\nGlobal runtime: {FACTORY.parent}")
        plans = []
        saved = read_json(journal) if journal and journal.exists() else None
        retired = read_json(project_dir(existing) / "retired.json", {}) if existing else {}
        if args.legacy:
            extra = args.legacy.resolve()
            previously_verified = str(extra) in retired or (saved and saved["root"] == str(extra))
            if extra != app and not previously_verified and (not (extra / BINDING).is_file() or binding(extra) != app):
                raise ValueError("the supplied legacy folder must be bound to this project")
            roots = sorted(set([*roots, extra]))
        if saved:
            roots = sorted(set([*roots, Path(saved["root"])]))
        for root in roots:
            print(f"Checking {root}")
            try:
                root.stat()
            except FileNotFoundError:
                if str(root) in retired:
                    continue
                raise
            plan = saved if saved and root == Path(saved["root"]) else inspect(root, app)
            if plan:
                plans.append(plan)
                print(f"History: {len(plan['history'])} jobs. Back up and retire:")
                for name in plan["files"]:
                    print(f"  {root / name}")
                for name in plan["kept_shared"]:
                    print(f"  Preserve shared file: {root / name}")
        if not plans:
            print("Already clean")
            return 0
        preview = [{k: v for k, v in plan.items() if k != "backup_id"} for plan in plans]
        fingerprint = digest(json.dumps(preview, sort_keys=True).encode())[:20]
        print(f"Preview ID: {fingerprint}")
        print(f"Verified backups will be stored under {HOME / 'backups'}")
        if args.expect and args.expect != fingerprint:
            raise ValueError("the migration preview has changed; review the new paths before applying")
        if not args.apply:
            print("Preview only. After approval, repeat with --apply.")
            return 0
        verify_install()
        project_id, state, _ = register(app)
        with exclusive_lock(state / "jobs/.lock"):
            if (state / "jobs/.owner").exists():
                raise BlockingIOError("a global run owns this project")
            for plan in plans:
                plan.setdefault("backup_id", uuid4().hex)
                apply_plan(plan, state, project_id, app)
        return 0
    except BlockingIOError as error:
        print(f"Pending: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError) as error:
        print(f"Needs review: {error}", file=sys.stderr)
        return 1
