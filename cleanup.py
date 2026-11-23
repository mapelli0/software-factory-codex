"""Preview or remove Software Factory installations below one directory."""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


SOURCE = Path(__file__).resolve().parent
MARKER = {"product": "software-factory-codex", "layout": "project-local-v1"}
SKILL = Path(".agents/skills/factory")
AGENTS = Path(".codex/agents")
BINDING = ".factory-project.local.json"
JOB_ID = re.compile(r"[0-9]{3,}-[a-z0-9-]+")
PROJECT_ID = re.compile(rb"[a-f0-9]{32}")
PORTABLE_KEYS = {"name", "concurrency", "max_rounds", "base_branch", "labels", "routing",
                 "surface_reviewers", "protected_paths", "ports", "checks"}


def data(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def linked(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def regular(path):
    return path.is_file() and path.resolve() == path


def git(*args):
    return subprocess.run(["git", "--no-optional-locks", *map(str, args)], capture_output=True)


def require_git(*args):
    result = git(*args)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace").strip() or "Git command failed")
    return result.stdout


def git_id(config):
    if not regular(config) or b"softwarefactory" not in config.read_bytes().lower():
        return None
    key = "softwarefactory.projectid"
    result = git("config", "--file", config, "--no-includes", "--get-all", key)
    if result.returncode == 1:
        return None
    value = result.stdout.strip()
    if result.returncode or not PROJECT_ID.fullmatch(value):
        raise ValueError(f"inspect nonstandard {key} in {config}")
    return value.decode()


def fingerprints():
    known = data(SOURCE / "factory/legacy-files.json")
    # Exact supplemental fingerprints for the generated Windows junction setup.
    known["AGENTS.md"].append("a3f2f60f5e451768458269761c78d36f241b447663930ace5b30e46b61d20ab1")
    known[".codex/config.toml"].append("4f1c356ad2101a291691f6052c139ddf4a3f7668c674bdad4bc47741a2ad355c")
    known[".gitignore"].append("e4c8d011353ce9eb1c7003547a33d436a51883c48b055a308d5cc5e9d8877ea1")
    known[(SKILL / "SKILL.md").as_posix()].append("9cf3ca957a580650d54fbf9ee6e67a5c14d1d42500f676d9fd5557fa95fdf6f9")
    return known


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def legacy_core(base, known):
    # Two independently fingerprinted entry points also identify a copy that
    # customized the third command for its project.
    matches = 0
    for command in ("route", "gate", "job"):
        name = "factory/bin/" + command
        if regular(base / name) and digest(base / name) in known[name]:
            matches += 1
            if matches == 2:
                return True
    return False


def factory_origin(base):
    config = base / ".git/config"
    if not regular(config):
        return False
    result = git("config", "--file", config, "--no-includes", "--get-all", "remote.origin.url")
    return result.returncode == 0 and bool(re.fullmatch(
        rb"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
        rb"mapelli0/software-factory-codex(?:\.git)?/?", result.stdout.strip(), re.IGNORECASE
    ))


def verify_clone(base, known):
    if SOURCE.is_relative_to(base) or Path.cwd().resolve().is_relative_to(base):
        raise ValueError(f"run cleanup from a separate copy and outside the selected clone: {base}")
    binding = base / BINDING
    if not regular(binding) or not legacy_core(base, known) or not factory_origin(base):
        raise ValueError(f"expected a bound clone of mapelli0/software-factory-codex: {base}")
    settings = data(binding)
    value = settings.get("checkout") if isinstance(settings, dict) else None
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError(f"invalid application binding at {binding}")
    app = Path(value).resolve(strict=True)
    if app.is_relative_to(base) or base.is_relative_to(app):
        raise ValueError(f"the bound application overlaps the clone at {base}")
    app_root = os.fsdecode(require_git("-C", app, "rev-parse", "--show-toplevel", "--verify", "HEAD"))
    if Path(app_root.splitlines()[0]).resolve() != app:
        raise ValueError(f"binding must identify the application checkout root: {binding}")
    gitdir = base / ".git"
    common = require_git("-C", base, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if gitdir.resolve() != gitdir or not gitdir.is_dir() or Path(os.fsdecode(common).strip()).resolve() != gitdir:
        raise ValueError(f"expected an ordinary clone owning its Git directory at {base}")
    listing = require_git("-C", base, "worktree", "list", "--porcelain", "-z")
    roots = [Path(os.fsdecode(line[9:])).resolve() for line in listing.split(b"\0") if line.startswith(b"worktree ")]
    if roots != [base] or b"bare\0" in listing:
        raise ValueError(f"the factory clone has extra worktrees or is not a working checkout: {base}")
    return app


@dataclass
class Plan:
    root: Path
    discard: bool
    orphan_settings: bool = False
    requested_clones: frozenset = frozenset()
    clones: dict = field(default_factory=dict)
    files: dict = field(default_factory=dict)
    trees: dict = field(default_factory=dict)
    links: set = field(default_factory=set)
    dirs: set = field(default_factory=set)
    keys: dict = field(default_factory=dict)
    worktrees: dict = field(default_factory=dict)
    installs: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    blockers: list = field(default_factory=list)

    def add_file(self, path, fingerprint=None):
        self.files[path] = fingerprint or digest(path)

    def add_tree(self, path):
        info = path.stat()
        self.trees[path] = (info.st_dev, info.st_ino)

    def prune_after(self, path, stop):
        while path != stop and path.is_relative_to(stop):
            self.dirs.add(path)
            path = path.parent


def owned_jobs(plan, base, checkout):
    """Identify job history and Git registrations before any file is removed."""
    jobs = base / "factory/jobs"
    workdir = base / ".worktrees"
    plan.installs[base] = checkout
    if jobs.resolve() != jobs or workdir.resolve() != workdir:
        raise ValueError(f"linked job or worktree directory under {base}")
    if (jobs / ".owner").exists():
        raise ValueError(f"a run owns {jobs}; release it after stopping its workers")
    if (base / ".factory-dashboard.local.json").exists():
        raise ValueError(f"stop the factory dashboard with python \"{base / 'factory/bin/dashboard.py'}\" stop")
    branches = {}
    if jobs.is_dir():
        for folder in jobs.iterdir():
            if folder.name == ".lock" and regular(folder):
                continue
            state = folder / "job.json"
            if not JOB_ID.fullmatch(folder.name) or not regular(state):
                raise ValueError(f"unrecognized job data at {folder}")
            job = data(state)
            if not isinstance(job, dict) or job.get("id") != folder.name:
                raise ValueError(f"invalid job identity at {state}")
            if job.get("stage") not in {"merged", "rejected"}:
                plan.notes.append(f"Unfinished job {folder} ({job.get('stage')})")
                if not plan.discard:
                    plan.blockers.append(f"finish {folder.name} or include --discard-jobs")
            branches[folder.name] = "refs/heads/factory/" + folder.name
        plan.add_tree(jobs)

    # Git can retain a registration even after a worktree folder has gone.
    if not (checkout / ".git").exists():
        if workdir.is_dir() and any(workdir.iterdir()):
            raise ValueError(f"checkout unavailable for worktrees at {workdir}")
        return
    records = require_git("-C", checkout, "worktree", "list", "--porcelain", "-z")
    registered = set()
    for record in records.rstrip(b"\0").split(b"\0\0"):
        lines = os.fsdecode(record).split("\0")
        worktree = Path(lines[0].removeprefix("worktree ")).absolute()
        if not worktree.is_relative_to(workdir):
            continue
        if worktree.parent != workdir or worktree.resolve() != worktree:
            raise ValueError(f"unexpected linked worktree at {worktree}")
        if "branch " + branches.get(worktree.name, "?") not in lines:
            raise ValueError(f"worktree branch does not match a factory job at {worktree}")
        if any(line.startswith(("locked", "prunable")) for line in lines):
            raise ValueError(f"resolve the locked or stale worktree at {worktree}")
        if require_git("-C", worktree, "status", "--porcelain", "--untracked-files=all"):
            raise ValueError(f"save uncommitted changes in {worktree}")
        ignored = require_git("-C", worktree, "ls-files", "--others", "--ignored", "--exclude-standard",
                              "--directory", "-z").rstrip(b"\0")
        if ignored:
            first = os.fsdecode(ignored.split(b"\0", 1)[0])
            plan.notes.append(f"Worktree contains ignored files, including {worktree / first}")
            if not plan.discard:
                plan.blockers.append(f"save ignored worktree files at {worktree} or include --discard-jobs")
        common = os.fsdecode(require_git("-C", checkout, "rev-parse", "--path-format=absolute",
                                         "--git-common-dir")).strip()
        if not Path(common).resolve().is_relative_to(plan.root):
            raise ValueError(f"include the checkout containing {common} in the scan to unregister {worktree}")
        plan.worktrees[worktree] = checkout
        plan.notes.append(f"Keep branch factory/{worktree.name}")
        registered.add(worktree)
    if workdir.exists():
        for entry in workdir.iterdir():
            if entry not in registered:
                raise ValueError(f"unregistered content in {workdir}: {entry.name}")
        plan.dirs.add(workdir)


def in_project(plan, base, project_id):
    marker = base / "installation.json"
    if regular(marker):
        try:
            identity = data(marker)
        except (UnicodeError, ValueError):
            identity = None
        if identity == MARKER:
            owned_jobs(plan, base, base.parent)
            plan.add_tree(base)
            return
    portable = base / "project.json"
    if regular(portable):
        try:
            values = data(portable)
        except (UnicodeError, ValueError):
            if project_id:
                raise ValueError(f"inspect invalid factory settings at {portable}")
            values = None
        if isinstance(values, dict) and set(values) <= PORTABLE_KEYS and (project_id or plan.orphan_settings):
            plan.add_file(portable)
            plan.dirs.add(base)
        else:
            plan.notes.append(f"Review ambiguous settings file {portable}")


def legacy(plan, base, known, core):
    # A source distribution can itself be inside a directory the user scans.
    if not (base / BINDING).exists() and (base / "CODEX-MIGRATION-PLAN.md").is_file() and (
        base / "docs/assets"
    ).is_dir():
        plan.notes.append(f"Preserve factory source checkout {base}")
        return
    recognized_links = []
    has_retained_link = False
    for rel in (SKILL, AGENTS):
        leaf = base / rel
        if leaf.parent.resolve() != leaf.parent or not linked(leaf):
            continue
        target = leaf.resolve()
        target_base = target.parents[len(rel.parts) - 1] if len(target.parts) > len(rel.parts) else None
        if target_base and target == target_base / rel and legacy_core(target_base, known):
            if regular(target_base / BINDING) and factory_origin(target_base) and (
                target_base.is_relative_to(plan.root) and target_base not in plan.requested_clones
                or (target_base / "factory/jobs/.owner").exists()
            ):
                plan.notes.append(f"Keep {leaf} for the retained or active factory clone at {target_base}")
                has_retained_link = True
                continue
            recognized_links.append(leaf)
            plan.links.add(leaf)
            plan.prune_after(leaf.parent, base)
    if not core and (not recognized_links or has_retained_link):
        return
    if core:
        binding = base / BINDING
        checkout = base
        if binding.exists():
            if not regular(binding):
                raise ValueError(f"inspect linked binding {binding}")
            settings = data(binding)
            value = settings.get("checkout") if isinstance(settings, dict) else None
            if not isinstance(value, str) or not Path(value).is_absolute():
                raise ValueError(f"inspect invalid binding {binding}")
            checkout = Path(value).resolve()
            plan.add_file(binding)
        owned_jobs(plan, base, checkout)
        for name in (".factory-dashboard.local.lock", ".factory-project.local.tmp", "PROJECT.local.md"):
            if regular(base / name):
                plan.add_file(base / name)
        local = base / ".factory-local"
        if regular(local / "install-report.md") and "Software Factory installation report" in (
            local / "install-report.md"
        ).read_text(encoding="utf-8-sig"):
            plan.add_tree(local)
        for name in ("config.json", "checks.ps1", "checks.sh"):
            if regular(base / "factory" / name):
                plan.add_file(base / "factory" / name)
    for name, hashes in known.items():
        path = base / name
        if not regular(path) or (not core and name not in {"AGENTS.md", ".codex/config.toml"}):
            continue
        checksum = digest(path)
        if checksum in hashes:
            plan.add_file(path, checksum)
        elif path not in plan.files:
            plan.notes.append(f"Review edited or shared file {path}")
    for path in list(plan.files):
        if path.is_relative_to(base):
            plan.prune_after(path.parent, base)
    cache = base / "factory/bin/__pycache__"
    if core and cache.resolve() == cache and cache.is_dir():
        for file in cache.iterdir():
            if regular(file) and re.fullmatch(r"(?:runtime|dashboard)\.[A-Za-z0-9.-]+\.pyc", file.name):
                plan.add_file(file)
                plan.prune_after(cache, base)


def scan(root, discard, orphan_settings=False, clone_paths=()):
    requested = set()
    for supplied in clone_paths:
        path = Path(os.path.abspath(supplied.expanduser()))
        if not path.is_relative_to(root) or path != supplied.expanduser().resolve(strict=True):
            raise ValueError(f"selected clone must be a physical directory inside {root}: {supplied}")
        requested.add(path)
    plan = Plan(root, discard, orphan_settings, frozenset(requested))
    known = fingerprints()
    ignored = {".git", "node_modules", "__pycache__", ".venv", ".pnpm-store"}
    for parent, dirs, files in os.walk(root, onerror=lambda e: plan.blockers.append(str(e))):
        base = Path(parent)
        names = set(dirs) | set(files)
        dirs[:] = [name for name in dirs if name not in ignored and not linked(base / name)]
        try:
            if base in requested:
                dirs.clear()
                app = verify_clone(base, known)
                owned_jobs(plan, base, app)
                plan.trees.pop(base / "factory/jobs", None)
                plan.clones[base] = app
                plan.add_tree(base)
                plan.notes.append(f"Remove entire legacy clone including .git, job history and all local edits: {base}")
                continue
            if BINDING in names and regular(base / BINDING) and legacy_core(base, known) and factory_origin(base):
                dirs.clear()
                plan.notes.append(f"Keep standalone factory clone and its job history: {base}. "
                                  f'To remove the whole clone, include --remove-legacy-clone "{base}".')
                continue
            project_id = None
            if ".git" in names:
                config = base / ".git/config"
                project_id = git_id(config)
                if project_id:
                    plan.keys[config] = project_id
            if base == root and base.name == ".factory":
                dirs.clear()
                in_project(plan, base, None)
                continue
            if ".factory" in dirs:
                folder = base / ".factory"
                if (folder / "installation.json").is_file() or (folder / "project.json").is_file():
                    dirs.remove(".factory")
                    in_project(plan, folder, project_id)
            if {"factory", ".agents", ".codex"} & names:
                core = "factory" in dirs and legacy_core(base, known)
                if core:
                    dirs[:] = [name for name in dirs if name not in {"factory", ".worktrees", ".factory-local"}]
                legacy(plan, base, known, core)
        except (OSError, ValueError, RuntimeError) as error:
            plan.blockers.append(f"{base}: {error}")
    for missing in requested - plan.clones.keys():
        plan.blockers.append(f"could not verify the selected legacy clone: {missing}")
    return plan


def checked(plan, path, *, leaf_link=False):
    resolved = path.parent.resolve() / path.name if leaf_link else path.resolve()
    if resolved != path or not resolved.is_relative_to(plan.root):
        raise ValueError(f"refusing changed or outside path {path}")


def remove_tree(path):
    def retry_readonly(func, name, exc_info):
        entry = Path(name)
        if (not isinstance(exc_info[1], PermissionError) or linked(entry)
                or not entry.resolve().is_relative_to(path) or os.access(entry, os.W_OK)):
            raise exc_info[1]
        os.chmod(entry, stat.S_IWRITE | stat.S_IREAD)
        func(name)

    shutil.rmtree(path, onerror=retry_readonly)


def verify_tree(plan, folder):
    checked(plan, folder)
    info = folder.stat()
    if (info.st_dev, info.st_ino) != plan.trees[folder]:
        raise ValueError(f"directory changed during scan: {folder}")
    if folder in plan.clones and verify_clone(folder, fingerprints()) != plan.clones[folder]:
        raise ValueError(f"application binding changed during scan: {folder}")
    if folder.name == ".factory":
        marker = folder / "installation.json"
        if not regular(marker) or data(marker) != MARKER:
            raise ValueError(f"factory ownership marker changed: {marker}")


def verify_file(plan, path):
    checked(plan, path)
    if not regular(path) or digest(path) != plan.files[path]:
        raise ValueError(f"file changed during scan: {path}")


def apply(plan):
    # A recursive scan can take time. Recheck runs and worktrees before removing
    # the first file. Git performs its own final dirty/locked check on removal.
    fresh = Plan(plan.root, plan.discard)
    for base, checkout in plan.installs.items():
        owned_jobs(fresh, base, checkout)
    if fresh.blockers or fresh.worktrees != plan.worktrees:
        raise ValueError("factory jobs or worktrees changed during the scan; preview again")
    for folder in plan.trees:
        verify_tree(plan, folder)
    for path in plan.files:
        verify_file(plan, path)
    for path, checkout in plan.worktrees.items():
        checked(plan, path)
        require_git("-C", checkout, "worktree", "remove", path)
    for path in plan.links:
        checked(plan, path, leaf_link=True)
        if not linked(path):
            raise ValueError(f"expected a directory link at {path}")
        if path.is_symlink():
            path.unlink()
        else:
            path.rmdir()  # Windows junction; remove the entry itself.
    for config, expected in plan.keys.items():
        checked(plan, config)
        require_git("config", "--file", config, "--unset-all", "softwarefactory.projectid", "^" + expected + "$")
    for folder in sorted(plan.trees, key=lambda p: len(p.parts), reverse=True):
        verify_tree(plan, folder)
        if folder.name == ".factory":
            # Keep the ownership marker until the last removal so a retry can
            # still identify this installation after an interrupted cleanup.
            for child in folder.iterdir():
                if child.name == "installation.json":
                    continue
                if linked(child):
                    if child.is_dir() and not child.is_symlink():
                        child.rmdir()
                    else:
                        child.unlink()
                elif child.is_dir():
                    checked(plan, child)
                    remove_tree(child)
                else:
                    child.unlink()
            (folder / "installation.json").unlink()
            folder.rmdir()
        else:
            remove_tree(folder)
    for file in sorted(plan.files, key=lambda p: p.parent.name == "bin"):
        verify_file(plan, file)
        file.unlink()
    for folder in sorted(plan.dirs, key=lambda p: len(p.parts), reverse=True):
        checked(plan, folder)
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="scan this directory and its descendants")
    parser.add_argument("--apply", action="store_true", help="remove the identified factory files")
    parser.add_argument("--discard-jobs", action="store_true",
                        help="discard unfinished job records and ignored files in clean job worktrees")
    parser.add_argument("--orphan-settings", action="store_true",
                        help="include unregistered .factory/project.json files using only known factory settings")
    parser.add_argument("--remove-legacy-clone", action="append", type=Path, default=[], metavar="DIRECTORY",
                        help="remove this verified standalone factory clone, including .git and local edits (repeatable)")
    args = parser.parse_args(argv)
    try:
        supplied = args.path.expanduser()
        root = Path(os.path.abspath(supplied))
        if root != supplied.resolve(strict=True) or not root.is_dir():
            raise ValueError("select a physical directory without symlink or junction components")
        plan = scan(root, args.discard_jobs, args.orphan_settings, args.remove_legacy_clone)
        for note in plan.notes:
            print(note)
        for paths, action in [(plan.links, "Unlink"), (plan.keys, "Unset softwarefactory.projectid in"),
                              (plan.worktrees, "Unregister worktree (keep branch)"), (plan.files, "Remove file"),
                              (plan.trees, "Remove directory and contents")]:
            for path in sorted(paths):
                print(f"{action}: {path}")
        if plan.blockers:
            for message in plan.blockers:
                print(f"Blocked: {message}", file=sys.stderr)
            return 1
        if not (plan.trees or plan.files or plan.links or plan.keys or plan.worktrees):
            print("No recognized factory files to remove.")
        elif args.apply:
            apply(plan)
            print("Cleanup complete.")
        else:
            print("Preview only. Repeat with --apply to remove the listed items.")
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Cleanup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
