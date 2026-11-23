# Software factory

For a new installation run `python install.py "<application checkout>"` from the factory source. Follow INSTALL.md for project checks and Codex startup. Resolve the application from the installed directory with `python factory/bin/job project`. Respect its AGENTS.md and the optional PROJECT.local.md inside the installation.

The Python entry points are `factory/bin/job`, `factory/bin/gate` and `factory/bin/route`. Job files and linked worktrees live in `factory/jobs/` and `.worktrees/` under the installation. The operator merges through GitHub or locally.

Disconnected intake collects a brief in chat. Start the job only after `/factory execute` or `$factory execute`. Verify changes to installation or cleanup with `python -m unittest discover -s tests -v` from the source checkout.
