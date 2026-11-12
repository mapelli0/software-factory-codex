# Software factory template

Install this template into an application repository using [INSTALL.md](INSTALL.md). Start Codex from the installed project's root and invoke `$factory` and choose GitHub or disconnected intake. In disconnected mode, collect the brief in chat and wait for `/factory execute` or `$factory execute` before starting the job. Keep application setup, validation and preview commands in that project's instructions.

The Python entry points are `factory/bin/job`, `factory/bin/gate` and `factory/bin/route`. Run them through Python on both platforms. The check placeholders in this template are intentionally incomplete until an application is installed. Job state belongs in `factory/jobs/` and worktrees in `.worktrees/`. The operator merges through GitHub or locally, according to the job mode.
