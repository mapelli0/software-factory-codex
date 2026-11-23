# Software Factory for Codex

A Windows-first port of the ZazenCodes Software Factory v2 for Claude Code. It uses a Codex skill and custom subagents to take a request through intake, specification, implementation, project checks and review. A person makes the final merge in GitHub or in local Git.

## Install in one project

Open a Codex chat in the Git project where you want the factory. Paste this prompt. The project must have at least one commit.

```text
Install Software Factory for the Git project open in this chat.
Clone https://github.com/mapelli0/software-factory-codex.git into a temporary
folder. Run its install.py with this project's Git root as the destination.
From the project root, run python .factory/factory/bin/job project and verify
it prints this project's path. Configure the local checks from the project's CI
and run preflight.
```

The installer writes only to `.factory/` inside the chosen project. That directory holds its skill, agent profiles, checks, job history and worktrees, and ignores itself in Git. You can also add `/.factory/` to the project's `.gitignore`. For a terminal install on a new machine, follow the [manual installation steps](INSTALL.md#install-from-github).

## Start a job

In a desktop chat opened at the application root, enter `Use .factory/.agents/skills/factory/SKILL.md for this project's factory`. In the CLI, launch from the application root with `codex -C .factory --add-dir (Get-Location).Path`, then enter `$factory`.

- **GitHub.** Label an open issue `factory`, then enter `$factory run 42` for issue 42 or `$factory run` for the queue. The factory hands you a reviewed PR to merge.
- **Disconnected.** Describe the request in chat, then send `/factory execute` or `$factory execute` when the brief is ready. The factory hands you a reviewed local branch.

Use `$factory status` to see progress or `$factory dashboard` to open this project's board. [Setup and validation](INSTALL.md) · [Runtime design](DESIGN.md) · [Example jobs](examples/jobs)

## Clean up and reinstall

Preview all recognized installations under a folder with `python cleanup.py "C:\Projects"`. Add `--apply` to remove them. To roll back the old account-wide installation, use `python uninstall_global.py` to preview and add `--apply` to execute. [Cleanup guide](INSTALL.md#remove-old-installations)

## Thanks and license

Thanks to [ZazenCodes](https://github.com/zazencodes) for creating and sharing [Software Factory for Claude Code v2](https://github.com/zazencodes/zazencodes-season-3/tree/main/src/software-factory-claude-code-v2). This port builds on its GitHub workflow, job state machine, quality gates and dashboard.

Distributed under [GPLv3](LICENSE). The upstream author offers separate commercial licensing.
