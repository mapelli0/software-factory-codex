# Software Factory for Codex

A Windows-first port of the ZazenCodes Software Factory v2 for Claude Code. It uses a Codex skill and custom subagents to take a request through intake, specification, implementation, project checks and review. A person makes the final merge in GitHub or in local Git.

## Install in one project

Open the application's Git root as the project in Codex. If the checkout is `C:\Projects\My App`, select `My App` in the folder picker. The project must have at least one commit. Paste this prompt.

```text
Install Software Factory for the Git project open in this chat.
Clone https://github.com/mapelli0/software-factory-codex.git into a temporary
folder. Run its install.py with this project's Git root as the destination.
From the project root, run python .factory/factory/bin/job project and verify
it prints this project's path. Configure the local checks from the project's CI
and run preflight.
```

The workflow, runtime, agent profiles, checks, jobs and worktrees live in `.factory/`. To make `$factory` visible in the application chat, the installer also creates a small `.agents/skills/factory/SKILL.md` file that points Codex to the workflow. Both directories include their own Git ignore rules.

If an existing per-project installation is missing `$factory` from the picker, rerun the latest installer for that checkout. Your jobs and customized checks stay in place. [Manual install and repair](INSTALL.md#install-from-github)

## Start a job

Open a chat in that same application folder, or start `codex` there in a terminal. Enter `$factory status` to see the project's jobs. If the picker still shows the old skill list after installation, restart Codex and reopen the application folder. Enter `$factory` to choose a workflow.

- **GitHub.** Label an open issue `factory`, then enter `$factory run 42` for issue 42 or `$factory run` for the queue. The factory hands you a reviewed PR to merge.
- **Disconnected.** Describe the request in chat, then send `/factory execute` or `$factory execute` when the brief is ready. The factory hands you a reviewed local branch.
- **OpenSpec.** Enter `$factory openspec` to list this project's open changes and choose one, or enter `$factory openspec <change-id>`. Intake reads the existing proposal, scenarios and tasks and asks about any gaps. The factory builds and reviews the change on a local branch. After you merge, tell the factory so it can verify the merge and mark the evidenced tasks complete through OpenSpec. The change stays available for a separate archive decision. [OpenSpec setup and usage](INSTALL.md#use-an-existing-openspec-change)

Use `$factory dashboard` to open this project's board. [Setup and validation](INSTALL.md) · [Runtime design](DESIGN.md) · [Example jobs](examples/jobs)

## Clean up and reinstall

Preview all recognized installations under a folder with `python cleanup.py "C:\Projects"`. Add `--apply` to remove them. To roll back the old account-wide installation, use `python uninstall_global.py` to preview and add `--apply` to execute. [Cleanup guide](INSTALL.md#remove-old-installations)

## Thanks and license

Thanks to [ZazenCodes](https://github.com/zazencodes) for creating and sharing [Software Factory for Claude Code v2](https://github.com/zazencodes/zazencodes-season-3/tree/main/src/software-factory-claude-code-v2). This port builds on its GitHub workflow, job state machine, quality gates and dashboard.

Distributed under [GPLv3](LICENSE). The upstream author offers separate commercial licensing.
