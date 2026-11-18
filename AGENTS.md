# Software factory

For a new installation, follow [INSTALL.md](INSTALL.md) and use the current local Codex project's primary folder as the factory destination when suitable. Resolve the application checkout and keep it separate. Start Codex from the factory folder and invoke `$factory`. The binding from `python factory/bin/job project` identifies the application checkout.

Use existing application instructions and the factory's optional `PROJECT.local.md` for setup, validation and preview. The Python entry points are `factory/bin/job`, `factory/bin/gate` and `factory/bin/route`. Job files and linked worktrees live in `factory/jobs/` and `.worktrees/` under this installation. The operator merges through GitHub or locally.

Disconnected intake collects a brief in chat. Start the job only after `/factory execute` or `$factory execute`.
