"""User-wide registry and per-project settings. No project is selected by importing this module."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from runtime import WINDOWS, exclusive_lock, replace_file

FACTORY = Path(__file__).resolve().parents[1]
VERSION = "3.0.0"


def data_parent():
    if not WINDOWS:
        return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    # In a packaged Codex session, LocalAppData can point inside a per-chat container.
    # The directory above Packages is the account's persistent (possibly redirected) LocalAppData.
    for part in local.parents:
        if part.name.lower() == "packages" and any(
            name.lower().startswith("#!sandbox.") for name in local.relative_to(part).parts
        ):
            return part.parent
    return local


DEFAULT_HOME = data_parent()
HOME = Path(os.environ.get("SOFTWARE_FACTORY_HOME") or DEFAULT_HOME / "software-factory-codex").expanduser().resolve()
REGISTRY = HOME / "registry.json"
REGISTRY_LOCK = HOME / "registry.lock"
PROJECT_FILE = ".factory/project.json"
ID_PATTERN = re.compile(r"[a-f0-9]{32}")


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        if default is None:
            raise
        return default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        replace_file(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def registry():
    return read_json(REGISTRY, {"projects": {}, "ports": {}})


def git(path, *args, check=True):
    result = subprocess.run(["git", "-C", str(path), *args], capture_output=True)
    if check and result.returncode:
        raise ValueError(result.stderr.decode("utf-8", "replace").strip() or "Git command failed")
    return result


def checkout_root(path=None):
    start = Path(path or os.environ.get("SOFTWARE_FACTORY_PROJECT") or Path.cwd()).resolve(strict=True)
    git(start, "rev-parse", "--verify", "HEAD")
    listing = git(start, "worktree", "list", "--porcelain", "-z").stdout
    first = os.fsdecode(listing.split(b"\0", 1)[0])
    if not first.startswith("worktree ") or git(start, "rev-parse", "--is-bare-repository").stdout.strip() == b"true":
        raise ValueError("select an application checkout with a committed HEAD")
    root = Path(first.removeprefix("worktree ")).resolve(strict=True)
    if root.is_relative_to(HOME) or HOME.is_relative_to(root):
        raise ValueError("the global data directory and application checkout must be separate")
    return root


def project_dir(project_id):
    if not ID_PATTERN.fullmatch(project_id):
        raise ValueError("invalid project ID")
    return HOME / "projects" / project_id


def merge_settings(base, overrides):
    if not isinstance(overrides, dict):
        raise ValueError("project settings must be a JSON object")
    result = dict(base)
    for key, value in overrides.items():
        if key not in base and key != "name":
            raise ValueError(f"unknown project setting: {key}")
        if key in {"routing", "surface_reviewers", "labels", "ports"}:
            if not isinstance(value, dict) or set(value) - set(base[key]):
                raise ValueError(f"invalid project setting: {key}")
            value = {**base[key], **value}
        elif key == "checks":
            if not isinstance(value, dict) or set(value) - {"windows", "linux"}:
                raise ValueError("checks must specify windows or linux")
            value = {**base[key], **value}
        result[key] = value
    return result


def origin_identity(root):
    """Compare clones without persisting remote credentials or repository URLs."""
    remote = git(root, "remote", "get-url", "origin", check=False).stdout.decode().strip()
    if not remote:
        return None
    parts = urlsplit(remote)
    if parts.hostname:
        identity = parts.hostname.lower() + parts.path.removesuffix(".git").rstrip("/")
    elif re.match(r"^[^/@:]+@[^/:]+:", remote):
        host, path = remote.split("@", 1)[1].split(":", 1)
        identity = host.lower() + "/" + path.removesuffix(".git").rstrip("/")
    else:
        identity = os.path.normcase(str((root / remote).resolve()))
    return hashlib.sha256(identity.encode()).hexdigest()


def project_settings(root, revision=None):
    if revision:
        present = git(root, "ls-tree", revision, "--", PROJECT_FILE).stdout
        return json.loads(git(root, "show", f"{revision}:{PROJECT_FILE}").stdout) if present else {}
    return read_json(root / PROJECT_FILE, {})


def config_for(root, state=None, revision=None):
    cfg = read_json(FACTORY / "config.json")
    if state:
        cfg = merge_settings(cfg, read_json(state / "settings.json", {}))
    cfg = merge_settings(cfg, project_settings(root, revision))
    for key in ("concurrency", "max_rounds"):
        if type(cfg[key]) is not int or cfg[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    for name in [cfg.get("name", root.name), cfg["base_branch"], *cfg["labels"].values()]:
        if not isinstance(name, str) or not name.strip() or any(ord(c) < 32 for c in name):
            raise ValueError("project name, branch and labels must be non-empty text")
    for table in (cfg["routing"], cfg["surface_reviewers"]):
        for roles in table.values():
            if not isinstance(roles, dict) or set(roles) - {"code", "ui", "ux", "security"} or not all(
                isinstance(model, str) and model for model in roles.values()
            ):
                raise ValueError("invalid reviewer routing")
    if git(root, "check-ref-format", "--branch", cfg["base_branch"], check=False).returncode:
        raise ValueError("invalid base_branch")
    paths = cfg["protected_paths"]
    if not isinstance(paths, list) or not all(isinstance(p, str) and p for p in paths):
        raise ValueError("protected_paths must be an array of patterns")
    for platform, recipe in cfg["checks"].items():
        if not isinstance(recipe, dict):
            raise ValueError(f"invalid {platform} check definition")
        if "commands" in recipe:
            commands = recipe["commands"]
            if set(recipe) != {"commands"} or not isinstance(commands, list) or not commands or not all(
                isinstance(command, list) and command and all(isinstance(s, str) and s for s in command)
                for command in commands
            ):
                raise ValueError("checks.commands must contain non-empty argument arrays")
        else:
            script = recipe.get("script")
            if not isinstance(script, str) or not script or Path(script).is_absolute() or ".." in Path(script).parts:
                raise ValueError("check script must be a relative path")
            if set(recipe) - {"shell", "script"} or recipe.get("shell") != ("pwsh" if platform == "windows" else "bash"):
                raise ValueError(f"invalid {platform} check interpreter")
    return cfg


def register(root):
    with exclusive_lock(REGISTRY_LOCK):
        db = registry()
        records = db["projects"]
        known = next((k for k, v in records.items() if Path(v["checkout"]) == root), None)
        marker = git(root, "config", "--local", "--get", "softwarefactory.projectid", check=False).stdout.decode().strip()
        if marker and not ID_PATTERN.fullmatch(marker):
            raise ValueError("invalid project ID in Git local configuration")
        if known and known != marker:
            raise ValueError("the registered folder now contains a different checkout; select the original checkout")
        origin = origin_identity(root)
        if origin and not (known or marker):
            duplicate = next((r for r in records.values() if r.get("origin") == origin), None)
            if duplicate:
                raise ValueError(f"another clone is registered for this remote; select {duplicate['checkout']} or its linked worktree")
        project_id = marker or known or uuid4().hex
        previous = records.get(project_id, {})
        if previous and Path(previous["checkout"]) != root:
            if Path(previous["checkout"]).exists():
                raise ValueError("project ID belongs to another existing checkout; select the intended clone")
            if any((project_dir(project_id) / "worktrees").glob("*")):
                raise ValueError("restore the original checkout path before resuming linked worktrees")
        state = project_dir(project_id)
        cfg = config_for(root, state)
        record = {**previous, "checkout": str(root), "origin": origin, "name": cfg.get("name", root.name), "concurrency": cfg["concurrency"]}
        if not marker:
            git(root, "config", "--local", "softwarefactory.projectid", project_id)
        if record != previous:
            records[project_id] = record
            write_json(REGISTRY, db)
    return project_id, state, cfg


def context():
    try:
        root = checkout_root()
        project_id, state, cfg = register(root)
        return root, project_id, state, cfg
    except (OSError, ValueError) as error:
        raise SystemExit(f"factory: {error}") from error


def validation_policy(root, state, revision):
    cfg = config_for(root, state, revision)
    protected = list(dict.fromkeys([PROJECT_FILE, *cfg["protected_paths"]]))
    checks = {}
    portable = project_settings(root, revision).get("checks", {})
    for platform, recipe in cfg["checks"].items():
        if "commands" in recipe:
            checks[platform] = recipe
            for command in recipe["commands"]:
                for arg in command:
                    path = Path(arg)
                    if path.suffix in {".ps1", ".sh", ".py", ".js", ".mjs", ".cjs"} and not path.is_absolute() and ".." not in path.parts:
                        protected.append(path.as_posix())
                if Path(command[0]).stem in {"npm", "pnpm", "yarn"}:
                    protected.extend(["package.json", "*/package.json"])
            continue
        script = recipe["script"]
        # The bundled placeholders and imported legacy checks live outside the application.
        legacy = state / "checks" / script
        if platform not in portable:
            source = legacy if legacy.is_file() else FACTORY / script
            contents = source.read_bytes()
        else:
            contents = git(root, "show", f"{revision}:{script}").stdout
            protected.append(script)
        digest = hashlib.sha256(contents).hexdigest()
        filename = digest + (".ps1" if platform == "windows" else ".sh")
        dest = state / "policies" / filename
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(uuid4().hex + ".tmp")
            tmp.write_bytes(contents)
            replace_file(tmp, dest)
        checks[platform] = {"shell": recipe["shell"], "script": filename}
        if platform in portable:
            checks[platform]["project_script"] = script
    return {"checks": checks, "protected_paths": sorted(set(protected)), "revision": revision}


def reserve_ports(project_id, job_id):
    with exclusive_lock(REGISTRY_LOCK):
        db = registry()
        leases = db.setdefault("ports", {})
        key = f"{project_id}/{job_id}"
        if key not in leases:
            used = set(leases.values())
            ports = read_json(FACTORY / "config.json")["ports"]
            for port in range(ports["base"], 65530, ports["step"]):
                if port not in used:
                    leases[key] = port
                    break
            else:
                raise ValueError("no available factory preview ports")
            write_json(REGISTRY, db)
        return leases[key]


def release_ports(project_id, job_id):
    with exclusive_lock(REGISTRY_LOCK):
        db = registry()
        if db.get("ports", {}).pop(f"{project_id}/{job_id}", None) is not None:
            write_json(REGISTRY, db)


def validate_job(project_id, state, job):
    if job.get("project_id") != project_id or not re.fullmatch(r"[0-9]{3,}-[a-z0-9-]+", job["id"]):
        raise ValueError("job belongs to another project or has an invalid ID")
    expected = state / "worktrees" / job["id"]
    if expected.resolve() != expected or Path(job["worktree"]).resolve() != expected:
        raise ValueError("job worktree differs from the registered location")
