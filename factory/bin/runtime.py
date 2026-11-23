"""Platform-specific primitives for the factory command line."""

import errno
import json
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from functools import cache
from pathlib import Path

WINDOWS = os.name == "nt"
PROJECT_FILE = ".factory-project.local.json"


def validate_checkout(checkout):
    """Return the selected Git worktree's root, requiring a committed HEAD."""
    project = Path(checkout).expanduser().resolve(strict=True)
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel", "--verify", "HEAD"],
        cwd=project, capture_output=True, encoding="utf-8", errors="replace",
    )
    roots = result.stdout.splitlines()
    if result.returncode != 0 or not roots or Path(roots[0]).resolve() != project:
        raise ValueError("select the root of an application Git checkout with a committed HEAD")
    return project


def validate_project(factory, checkout):
    """Check an explicit binding requested by a legacy installation."""
    home = factory.parent.resolve()
    project = validate_checkout(checkout)
    if project.is_relative_to(home) or home.is_relative_to(project):
        raise ValueError("the application checkout and separate factory directory must not overlap")
    return project


@cache
def project_checkout(factory):
    """Find the enclosing project, or resolve a legacy factory binding."""
    home = factory.parent
    if home.name == ".factory" and (home / "installation.json").is_file():
        return validate_checkout(home.parent)
    binding = home / PROJECT_FILE
    if not binding.exists():
        return factory.parent
    settings = json.loads(binding.read_text(encoding="utf-8"))
    checkout = settings.get("checkout") if isinstance(settings, dict) else None
    if not isinstance(checkout, str) or not Path(checkout).is_absolute():
        raise ValueError(f"{PROJECT_FILE} must contain an absolute checkout path")
    return validate_project(factory, checkout)


def check_job_checkout(factory, project, job):
    bound = job.get("project_checkout")
    if bound is None and project == factory.parent:
        return  # legacy in-repository jobs
    if not bound or Path(bound).resolve() != project:
        raise ValueError(f"{job['id']}: job belongs to a different application checkout")
    worktrees = factory.parent / ".worktrees"
    expected = worktrees / job["id"]
    if Path(job["worktree"]).resolve() != expected or expected.resolve() != expected:
        raise ValueError(f"{job['id']}: worktree must be under the factory directory")


if WINDOWS:
    import msvcrt
else:
    import fcntl


@contextmanager
def exclusive_lock(path):
    """Hold one checkout-wide lock for each state command."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if WINDOWS:
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    time.sleep(0.1)
        else:
            fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def check_command(factory, config):
    platform = "windows" if WINDOWS else "linux"
    default = ("pwsh", "checks.ps1") if WINDOWS else ("bash", "checks.sh")
    settings = config.get("checks", {}).get(platform, {})
    shell = settings.get("shell", default[0])
    script = settings.get("script", default[1])
    entry = (factory / script).resolve()
    if not entry.is_relative_to(factory.resolve()) or not entry.is_file():
        raise FileNotFoundError(f"Factory check script not found: {entry}")
    executable = shutil.which(shell)
    if not executable:
        raise FileNotFoundError(f"Factory check interpreter not found: {shell}")
    args = ["-NoProfile", "-NonInteractive", "-File"] if WINDOWS else []
    return [executable, *args, str(entry)]


def run_checks(factory, config, worktree):
    cmd = check_command(factory, config)
    return subprocess.run(
        cmd, cwd=worktree, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace",
    )
