# Software factory

Use INSTALL.md for installation and updates. Install the runtime and factory-prefixed roles once per user. Start a fresh Codex chat in the application and invoke `$factory`. Resolve the global launcher beside the installed skill. Use its `status` command to verify the selected application, runtime and local jobs directory.

Respect the application's AGENTS.md and portable settings in `.factory/project.json`. The project-specific job directory and linked worktrees live in user data. The operator merges every GitHub PR or disconnected branch. Disconnected intake waits for `/factory execute` or `$factory execute`.

Route `$factory cleanup` to the current project's migration preview. Apply the reviewed migration after operator approval. Run the native integration suite with `python -m unittest discover -s tests -v` when changing installation, job ownership, migration or dashboard behavior.
