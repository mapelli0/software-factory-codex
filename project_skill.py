"""Project-root entry that makes the installed workflow visible to Codex."""

from pathlib import Path


SKILL_DIR = Path(".agents/skills/factory")
ENTRY_FILES = {
    ".gitignore": "# Software Factory for Codex project skill\n/.gitignore\n/SKILL.md\n",
    "SKILL.md": """---
name: factory
description: Run this project's Software Factory. Use for $factory, job status, dashboard, GitHub intake, and disconnected jobs.
---

Read and follow the full factory skill at `.factory/.agents/skills/factory/SKILL.md`
relative to the project root containing this entry. Use that file as the skill's
real path and run its factory commands from the project's `.factory` directory.
Pass through the user's original request and arguments.
""",
}
