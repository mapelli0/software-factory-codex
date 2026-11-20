"""Platform-specific primitives for the factory command line."""

import errno
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

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


def replace_file(source, destination):
    """Allow brief Windows sharing violations while the live board reads state."""
    for attempt in range(10):
        try:
            source.replace(destination)
            return
        except PermissionError as error:
            if not WINDOWS or error.winerror not in (5, 32) or attempt == 9:
                raise
            time.sleep(0.025)


def run_checks(directory, config, worktree):
    platform = "windows" if WINDOWS else "linux"
    recipe = config["checks"][platform]
    commands = recipe.get("commands")
    if commands is None:
        entry = (directory / recipe["script"]).resolve(strict=True)
        if not entry.is_relative_to(directory.resolve()):
            raise ValueError("invalid check script location")
        if "project_script" in recipe:
            root = Path(worktree).resolve()
            project_entry = root / recipe["project_script"]
            if project_entry.resolve() != project_entry or not project_entry.is_relative_to(root):
                raise ValueError("check script points outside the job worktree")
            if project_entry.read_bytes().replace(b"\r\n", b"\n") != entry.read_bytes().replace(b"\r\n", b"\n"):
                raise ValueError("check script differs from the trusted job policy")
            entry = project_entry
        flags = ["-NoProfile", "-NonInteractive", "-File"] if WINDOWS else []
        commands = [[recipe["shell"], *flags, str(entry)]]
    output = []
    for command in commands:
        executable = shutil.which(command[0])
        if not executable:
            raise FileNotFoundError(f"check command not found: {command[0]}")
        result = subprocess.run([executable, *command[1:]], cwd=worktree, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, encoding="utf-8", errors="replace")
        output.append(result.stdout)
        if result.returncode:
            break
    return subprocess.CompletedProcess(commands, result.returncode, "\n".join(output))
