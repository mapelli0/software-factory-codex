# Software Factory for Codex on Windows

A Windows-first port of the ZazenCodes Software Factory v2 for Claude Code. It uses a Codex skill and custom subagents to take a request through intake, specification, implementation, project checks and review. A person makes the final merge in GitHub or in local Git.

## Install by pointing Codex at this repo

Install once per computer. Paste this prompt into Codex.

```text
Install the global Windows Software Factory from the main branch of
https://github.com/mapelli0/software-factory-codex.git using INSTALL.md.
Offer to scan my project folders for older installations. Show the launcher
path and how to verify it from a fresh application chat.
```

The installer puts one runtime and nine factory roles in the user's Codex folders. Open any application checkout and invoke `$factory`. Jobs and linked worktrees are kept outside the application. A project can commit `.factory/project.json` for its display name, job limit, branch, labels and platform checks. For setup, a C# and React example, or updates, see the [installation guide](INSTALL.md).

## Start a job

In the application chat, choose an intake mode.

- **GitHub.** Label an open issue `factory`, then enter `$factory run 42` for issue 42 or `$factory run` for the queue. The factory builds and reviews the change and hands you a PR to merge.
- **Disconnected.** Describe the request in chat. The intake agent helps scope it and waits for `/factory execute` or `$factory execute`. The factory uses the conversation as the issue brief and hands you a local branch. A GitHub remote is optional in this mode.

Use `$factory status` to see progress and what needs your attention. You can give feedback on a job and resume from its saved state.

## Local dashboard

The factory starts a local dashboard at the beginning of a run and posts the link in chat. Keep the tab open to follow stage changes, checks and reviews. The dashboard is available on the machine running the factory and stays up after the run.

The board opens on **All projects**. Each card and detail view names its project. Use the project selector to see how many slots each application is using. To reopen the board, invoke `$factory dashboard`. Use `$factory cleanup` in an application to check for an older installation, preview its migration, and verify the result after cutover.

The dashboard displays job artifacts and check output. The [historical examples](examples/jobs) show what the workflow records. See [DESIGN.md](DESIGN.md) for the runtime and the [migration plan](CODEX-MIGRATION-PLAN.md) for the porting decisions and pending verification.

## Thanks and license

Thanks to [ZazenCodes](https://github.com/zazencodes) for creating and sharing [Software Factory for Claude Code v2](https://github.com/zazencodes/zazencodes-season-3/tree/main/src/software-factory-claude-code-v2). This port builds on its GitHub workflow, job state machine, quality gates and dashboard.

Distributed under [GPLv3](LICENSE). The upstream author offers separate commercial licensing.
