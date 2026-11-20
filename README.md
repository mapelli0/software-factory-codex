# Software Factory for Codex on Windows

A Windows-first port of the ZazenCodes Software Factory v2 for Claude Code. It uses a Codex skill and custom subagents to take a request through intake, specification, implementation, project checks and review. A person makes the final merge in GitHub or in local Git.

<a name="install-by-pointing-codex-at-this-repo"></a>

## Install from a Codex chat

Open any local Codex chat on Windows and paste this message. Codex handles the download and installs the factory once for your Windows account.

```text
Install Software Factory for all my Codex projects on this Windows computer.
Download https://github.com/mapelli0/software-factory-codex to a temporary
folder and run python install.py. Set up reusable write access to the shared
factory data folder. Keep any permission settings I've already chosen.
Verify the skill and all nine agents, and tell me whether folder access was
configured or needs my attention.
```

Open a fresh chat in one of your Git projects. If the installer configured folder access, choose **Custom (config.toml)** in the chat's permissions control if needed. Type `$factory status` to see the selected project and factory version. For an older per-project installation, type `$factory cleanup` to preview its migration. [How folder access works](INSTALL.md#shared-folder-permissions)

Projects can share settings such as job limits and validation commands in `.factory/project.json`. See the [installation guide](INSTALL.md) for prerequisites, updates, and a C# and React example.

## Start a job

In the application chat, choose an intake mode.

- **GitHub.** Label an open issue `factory`, then enter `$factory run 42` for issue 42 or `$factory run` for the queue. The factory builds and reviews the change and hands you a PR to merge.
- **Disconnected.** Describe the request in chat. The intake agent helps scope it and waits for `/factory execute` or `$factory execute`. The factory uses the conversation as the issue brief and hands you a local branch. A GitHub remote is optional in this mode.

Use `$factory status` to see progress and what needs your attention. You can give feedback on a job and resume from its saved state.

## Local dashboard

At the start of each run or resume, the factory posts the dashboard's clickable local address in the project chat. Type **`$factory dashboard`** to get the live address again. Keep the tab open to follow stage changes, checks and reviews. The dashboard is available on the machine running the factory and stays up after the run.

The board opens on **All projects**. Each card and detail view names its project. Use the project selector to see how many slots each application is using. Use `$factory cleanup` in an application to check for an older installation, preview its migration, and verify the result after cutover. If a job repeatedly asks for permission to save reports, run **`$factory doctor <job-id>`** in that chat. [Troubleshooting repeated approvals](INSTALL.md#if-a-run-keeps-asking-for-approval)

The dashboard displays job artifacts and check output. The [historical examples](examples/jobs) show what the workflow records. See [DESIGN.md](DESIGN.md) for the runtime and the [migration plan](CODEX-MIGRATION-PLAN.md) for the porting decisions and pending verification.

## Thanks and license

Thanks to [ZazenCodes](https://github.com/zazencodes) for creating and sharing [Software Factory for Claude Code v2](https://github.com/zazencodes/zazencodes-season-3/tree/main/src/software-factory-claude-code-v2). This port builds on its GitHub workflow, job state machine, quality gates and dashboard.

Distributed under [GPLv3](LICENSE). The upstream author offers separate commercial licensing.
