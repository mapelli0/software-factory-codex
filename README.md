# Software Factory for Codex on Windows

A Windows-first port of the ZazenCodes Software Factory v2 for Claude Code. It uses a Codex skill and custom subagents to take a request through intake, specification, implementation, project checks and review. A person makes the final merge in GitHub or in local Git.

## Install by pointing Codex at this repo

Open Codex in the **application repository** where you want the factory, then paste this prompt.

```text
Install Software Factory for Codex in the current repository using
https://github.com/mapelli0/software-factory-codex.git

Read INSTALL.md in that repository and follow it. Copy the factory skill,
agent profiles and runtime into this project. Merge the factory settings
with any existing Codex configuration and project instructions.

Configure the Windows PowerShell checks using this project's CI commands.
Use its existing .NET SDK, solution, frontend workspace and package manager
where applicable. Run the factory preflight and show me what changed, the
checks that ran, and how to start my first job.
```

Use Git, a committed checkout, Python 3.11 or later, PowerShell 7 and a Codex client with custom subagents. GitHub mode also needs an authenticated GitHub CLI. For the files to copy, C#/.NET and React setup, and first-run verification, see the [installation guide](INSTALL.md). The runtime selects PowerShell on native Windows and Bash on Linux or WSL. The documented pilot targets Windows.

## Start a job

Enter `$factory` and choose a mode.

- **GitHub.** Label an open issue `factory`, then enter `$factory run 42` for issue 42 or `$factory run` for the queue. The factory builds and reviews the change and hands you a PR to merge.
- **Disconnected.** Describe the request in chat. The intake agent helps scope it and waits for `/factory execute` or `$factory execute`. The factory uses the conversation as the issue brief and hands you a local branch. A GitHub remote is optional in this mode.

Use `$factory status` to see progress and what needs your attention. You can give feedback on a job and resume from its saved state.

## Local dashboard

Run the following from the application repository root and open the [local dashboard](http://127.0.0.1:8000/dashboard.html).

```powershell
python -m http.server --bind 127.0.0.1 --directory factory
```

The dashboard displays job artifacts and check output. The [historical examples](examples/jobs) show what the workflow records. See [DESIGN.md](DESIGN.md) for the runtime and the [migration plan](CODEX-MIGRATION-PLAN.md) for the porting decisions and pending verification.

## Thanks and license

Thanks to [ZazenCodes](https://github.com/zazencodes) for creating and sharing [Software Factory for Claude Code v2](https://github.com/zazencodes/zazencodes-season-3/tree/main/src/software-factory-claude-code-v2). This port builds on its GitHub workflow, job state machine, quality gates and dashboard.

Distributed under [GPLv3](LICENSE). The upstream author offers separate commercial licensing.
