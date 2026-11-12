"""Platform-specific primitives for the factory command line."""

import errno
import os
import shutil
import subprocess
import time
from contextlib import contextmanager

WINDOWS = os.name == "nt"

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
