"""Read active OpenSpec changes and freeze the selected change for factory intake."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


CHANGE_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# OpenSpec's apply instructions recognize Markdown checkboxes at the start of a line.
CHECKBOX_PATTERNS = [
    re.compile("^(" + indent + r"[-*][^\S\r\n]*\[)([ xX])(\][^\S\r\n]*)([^\r\n]+)", re.MULTILINE)
    for indent in ("", r"[ \t]*")
]


def _nearest_planning(project):
    return next((p for p in (project, *project.parents) if (p / "openspec").is_dir()), None)


def _executable(project):
    planning = _nearest_planning(project) or project
    directories = []
    for directory in (project, *project.parents):
        directories.append(directory / "node_modules" / ".bin")
        if directory == planning:
            break
    # Search explicit PATH entries. On Windows shutil.which can also search the
    # process working directory, which may be an entirely different repository.
    directories.extend(Path(p.strip('"')) for p in os.get_exec_path() if Path(p.strip('"')).is_absolute())
    names = ("openspec.exe", "openspec.cmd", "openspec.bat") if os.name == "nt" else ("openspec",)
    for directory in directories:
        for name in names:
            candidate = directory / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
    raise ValueError("OpenSpec CLI not found. Install it for the project or add openspec to PATH.")


class _CommandError(ValueError):
    """OpenSpec ran and returned a failing exit code."""


def _query(project, *args, cwd=None):
    executable = _executable(project)
    env = {**os.environ, "OPENSPEC_TELEMETRY": "0", "NO_COLOR": "1"}
    command = [executable, *args, "--json"]
    if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".bat"}:
        # npm shims run in cmd.exe. Keep the path in a quoted environment variable.
        # Every argument is a fixed CLI option or a validated change ID.
        env["FACTORY_OPENSPEC_SHIM"] = str(executable)
        shell = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
        command = f'"{shell}" /d /v:off /s /c ""%FACTORY_OPENSPEC_SHIM%" {" ".join(args)} --json"'
    result = subprocess.run(command, cwd=cwd or project, env=env, stdin=subprocess.DEVNULL,
                            capture_output=True, encoding="utf-8", errors="replace")
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise _CommandError(f"openspec {' '.join(args)} failed: {detail or result.returncode}")
    try:
        output = json.loads(result.stdout)
    except ValueError as error:
        raise ValueError(f"openspec {' '.join(args)} returned invalid JSON") from error
    if not isinstance(output, dict):
        raise ValueError(f"openspec {' '.join(args)} returned an unexpected JSON response")
    return output


def _identifier(name):
    if (not isinstance(name, str) or len(name) > 200 or name == "archive"
            or not CHANGE_NAME.fullmatch(name)):
        raise ValueError(f"invalid OpenSpec change ID {name!r}; use the exact kebab-case ID from openspec list")
    return name


def _planning_root(project, report, fallback=None):
    if "root" in report:
        reported = report["root"]
        if not isinstance(reported, dict) or not isinstance(reported.get("path"), str):
            raise ValueError("invalid root in OpenSpec response")
        root = Path(reported["path"])
    else:
        # Older 1.x clients omit root. Retain the selected scope across follow-up queries.
        root = fallback or _nearest_planning(project)
    if root is None or not (root / "openspec").is_dir():
        raise ValueError(f"no project OpenSpec planning directory at or above {project}")
    if not project.is_relative_to(root) or root.resolve() != root:
        raise ValueError(f"OpenSpec selected a planning root outside the application's ancestry: {root}")
    changes = root / "openspec" / "changes"
    if changes.resolve() != changes:
        raise ValueError(f"OpenSpec changes directory is redirected: {changes}")
    return root


def _list_query(project):
    nearest = _nearest_planning(project)
    try:
        listing = _query(project, "list")
    except _CommandError as error:
        if nearest in (None, project):
            raise
        initial_error = error
    else:
        if "root" in listing or nearest in (None, project):
            return listing, project
        if not isinstance(listing.get("changes"), list):
            raise ValueError("openspec list omitted its changes array")
        initial_error = None

    # Earlier 1.x CLIs look only in cwd. Keep the CLI from the application
    # installation, but run its commands in the nearest verified planning root.
    root = _planning_root(project, {}, fallback=nearest)
    listing = _query(project, "list", cwd=root)
    if initial_error and "root" in listing:
        # Root-aware clients already resolved the app's configuration. An
        # error there must not silently select different planning data.
        raise initial_error
    return listing, root


def _listing(project):
    listing, query_cwd = _list_query(project)
    root = _planning_root(project, listing, fallback=query_cwd)
    if not isinstance(listing.get("changes"), list):
        raise ValueError("openspec list omitted its changes array")
    rows = []
    seen = set()
    for row in listing["changes"]:
        if not isinstance(row, dict):
            raise ValueError("invalid entry in openspec list")
        name = _identifier(row.get("name"))
        if name in seen:
            raise ValueError(f"openspec list returned duplicate change {name}")
        seen.add(name)
        total, done = row.get("totalTasks"), row.get("completedTasks")
        if type(total) is not int or type(done) is not int or not 0 <= done <= total:
            raise ValueError(f"invalid OpenSpec task counts for {name}")
        status = "no-tasks" if not total else "complete" if total == done else "in-progress"
        rows.append({"name": name, "totalTasks": total, "completedTasks": done, "status": status})
    return {"root": str(root), "changes": rows}, query_cwd


def list_changes(project):
    """Return the planning root and task counts for each active change, including drafts."""
    listing, _ = _listing(Path(project).resolve(strict=True))
    return listing


def _documents(change_dir, status, apply):
    """Load only outputs declared by the schema or the apply operation, inside this change."""
    documents = {}
    groups = {}

    def add(artifact, raw, *, pattern=False):
        if not isinstance(raw, str) or not raw:
            raise ValueError(f"invalid OpenSpec artifact path for {artifact}")
        path = change_dir / raw
        if ".." in path.parts or not path.is_relative_to(change_dir) or path == change_dir:
            raise ValueError(f"OpenSpec artifact outside selected change: {raw}")
        rel = path.relative_to(change_dir)
        if any(part.lower() == ".git" for part in rel.parts):
            raise ValueError(f"unexpected Git metadata in OpenSpec artifacts: {raw}")
        matches = change_dir.glob(rel.as_posix()) if pattern else [path]
        for entry in matches:
            if entry.resolve() != entry or not entry.is_file():
                raise ValueError(f"missing or linked OpenSpec artifact: {entry}")
            key = entry.relative_to(change_dir).as_posix()
            if key not in documents:
                documents[key] = entry.read_bytes().decode("utf-8")
            groups.setdefault(artifact, set()).add(key)

    for artifact, outputs in status.get("artifactPaths", {}).items():
        existing = outputs["existingOutputPaths"]
        if not isinstance(existing, list):
            raise ValueError(f"invalid list of OpenSpec artifact paths for {artifact}")
        for path in existing:
            add(artifact, path)
    for artifact, outputs in apply["contextFiles"].items():
        # Early clients returned a string (including output globs); current ones return lists.
        if isinstance(outputs, str):
            add(artifact, outputs, pattern=any(char in outputs for char in "*?["))
        elif isinstance(outputs, list):
            for path in outputs:
                add(artifact, path)
        else:
            raise ValueError(f"invalid OpenSpec context paths for {artifact}")
    for artifact in status.get("artifacts", []):
        if artifact["status"] == "done" and artifact["id"] not in groups:
            add(artifact["id"], artifact["outputPath"], pattern=True)
            if artifact["id"] not in groups:
                raise ValueError(f"missing declared OpenSpec output: {artifact['outputPath']}")
    return documents, groups


def _scope_digest(name, schema, documents, groups, tasks):
    # Locate the tracking file even when a custom schema gives its artifact a different ID.
    # A checkbox in a proposal, design or acceptance criterion is part of the scope itself.
    contents = documents.copy()
    tracking_file = None
    if tasks:
        rows = [(task["description"], task["done"]) for task in tasks]
        matching = {}
        for path, body in documents.items():
            # Match only boxes the installed CLI actually counted. Some versions or
            # schemas accept indented boxes, while 1.7's default parser ignores them.
            for pattern in CHECKBOX_PATTERNS:
                parsed = [(m[4].strip(), m[2].lower() == "x") for m in pattern.finditer(body)]
                if parsed == rows:
                    matching[path] = pattern
                    break
        declared = [path for path in matching if path in groups.get("tasks", ())]
        tracking = declared or list(matching)
        if len(tracking) != 1:
            raise ValueError("cannot identify a single declared OpenSpec tracking file matching the live tasks")
        tracking_file = tracking[0]
        contents[tracking_file] = matching[tracking_file].sub(r"\g<1> \g<3>\g<4>", contents[tracking_file])
    contents = {path: body.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
                for path, body in contents.items()}
    scope = [name, schema, contents, [(t["id"], t["description"]) for t in tasks]]
    digest = hashlib.sha256(json.dumps(scope, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return digest, tracking_file


def inspect_change(project, name):
    """Read the selected change; keep progress separate from its implementation scope."""
    _identifier(name)
    project = Path(project).resolve(strict=True)
    listing, query_cwd = _listing(project)
    if name not in {row["name"] for row in listing["changes"]}:
        raise ValueError(f"OpenSpec change {name!r} is not active at {listing['root']}")
    root = Path(listing["root"])
    changes = root / "openspec" / "changes"
    change_dir = changes / name
    if not change_dir.is_dir() or change_dir.resolve() != change_dir:
        raise ValueError(f"missing or linked OpenSpec change: {change_dir}")

    status = _query(project, "status", "--change", name, cwd=query_cwd)
    apply = _query(project, "instructions", "apply", "--change", name, cwd=query_cwd)
    try:
        for report in (status, apply):
            if report["changeName"] != name or _planning_root(project, report, fallback=root) != root:
                raise ValueError(f"OpenSpec changed the selected planning source or ID for {name}")
        for raw, expected in ((status.get("changeRoot"), change_dir), (apply.get("changeDir"), change_dir),
                              (status.get("planningHome", {}).get("root"), root),
                              (status.get("planningHome", {}).get("changesDir"), changes)):
            if raw is not None and Path(raw) != expected:
                raise ValueError(f"unexpected OpenSpec path for {name}: {raw}")
        schema = status["schemaName"]
        if not isinstance(schema, str) or not schema or apply.get("schemaName", schema) != schema:
            raise ValueError(f"inconsistent OpenSpec schema for {name}")
        action = status.get("actionContext", {})
        kind = status.get("planningHome", {}).get("kind", "repo")
        mode = action.get("mode", "workspace-planning" if kind == "workspace" else "repo-local")
        if mode not in {"repo-local", "workspace-planning"}:
            raise ValueError(f"unknown OpenSpec action mode {mode!r}")
        if mode == "repo-local":
            if kind != "repo" or action.get("requiresAffectedAreaSelection") or (
                "allowedEditRoots" in action and not any(Path(path) == root for path in action["allowedEditRoots"])
            ):
                raise ValueError(f"OpenSpec does not permit repo-local changes at {root}")
        state, tasks, progress = apply["state"], apply["tasks"], apply["progress"]
        if state not in {"ready", "blocked", "all_done"} or not isinstance(tasks, list):
            raise ValueError(f"invalid OpenSpec apply state or tasks for {name}")
        normalized_tasks = []
        ids = set()
        for task in tasks:
            task_id = task["id"]
            if (not isinstance(task_id, str) or not task_id or task_id in ids
                    or not isinstance(task["description"], str) or not task["description"].strip()
                    or type(task["done"]) is not bool):
                raise ValueError(f"invalid or duplicate OpenSpec task in {name}")
            ids.add(task_id)
            normalized_tasks.append({"id": task_id, "description": task["description"], "done": task["done"]})
        complete = sum(task["done"] for task in tasks)
        counts = {"total": len(tasks), "complete": complete, "remaining": len(tasks) - complete}
        if any(type(progress.get(k)) is not int or progress[k] != v for k, v in counts.items()):
            raise ValueError(f"inconsistent OpenSpec progress for {name}")
        if state == "all_done" and (not tasks or counts["remaining"]):
            raise ValueError(f"OpenSpec reports all_done without a completed checklist for {name}")
        missing = apply.get("missingArtifacts", [])
        if not isinstance(missing, list) or not all(isinstance(a, str) and a for a in missing):
            raise ValueError(f"invalid list of missing OpenSpec artifacts for {name}")
        documents, groups = _documents(change_dir, status, apply)
        digest, tracking = _scope_digest(name, schema, documents, groups, normalized_tasks)
        return {"name": name, "root": str(root), "change_dir": str(change_dir), "schema": schema,
                "mode": mode, "state": state, "progress": counts, "tasks": normalized_tasks,
                "documents": documents, "scope_digest": digest, "tracking_file": tracking, "missing_artifacts": missing}
    except (AttributeError, KeyError, TypeError, UnicodeError) as error:
        raise ValueError(f"could not read OpenSpec metadata or UTF-8 artifacts for {name}: {error}") from error
