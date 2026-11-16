# Install the factory beside an application checkout

Use [mapelli0/software-factory-codex](https://github.com/mapelli0/software-factory-codex) as the source for the factory files.

## Choose two folders

Before creating or changing files, ask the operator for both paths and wait for their answers.

1. Which folder contains the application code? Choose the root of an existing Git checkout with a committed HEAD.
2. Where should the factory be installed? Choose a separate folder, such as a sibling of the application checkout.

Resolve both paths. The folders must be distinct and neither can contain the other. Use one factory directory per application checkout. Keep the skill, agent profiles, checks, dashboard, job files and linked worktrees in the factory folder.

## Set up the factory

1. Verify Git, Python 3.11+, and a Codex client with custom subagents. Use PowerShell 7 on native Windows or Bash on Linux or WSL. For GitHub mode, the **application checkout** needs a GitHub `origin`, an authenticated `gh` with access to that repository, and the configured factory labels. Disconnected mode can use a checkout without a remote.
2. In the factory folder, copy `.agents/skills/factory/`, the nine profiles under `.codex/agents/`, `factory/`, `AGENTS.md`, `INSTALL.md` and `LICENSE`. Merge `.codex/config.toml` and the factory ignore rules into that folder's existing configuration. Preserve existing instructions and license notices. If using a fresh clone of the factory repository as the installation, the template files are already there.
3. From the factory folder, bind it to the chosen application checkout. The binding is stored locally in `.factory-project.local.json`.

   ```powershell
   python factory/bin/job configure "C:\path to\application"
   python factory/bin/job project
   ```

4. In the **factory folder**, configure `factory/config.json` using the application's GitHub base branch and label names when applicable. Fill in `factory/checks.ps1` for Windows or `factory/checks.sh` for Linux/WSL using the application's actual CI commands. The scripts run with the application checkout or linked worktree as their working directory. Keep checks non-interactive, preserve exit codes, and check `$LASTEXITCODE` immediately after native commands in PowerShell.
5. Record any missing setup, validation and preview instructions in `PROJECT.local.md` in the factory directory. Use existing application instructions and CI as sources. For C#/.NET, record the SDK and solution or project. For React, record the Node version, workspace, package manager and relevant scripts. For mixed apps, document how the frontend talks to the backend on the job's ports. Keep machine-specific configuration, job files, and worktrees ignored as specified by the factory's `.gitignore`.
6. From the factory folder, run `python factory/bin/gate --preflight`. This tests the selected application checkout without writing a job verdict. In GitHub mode, use `python factory/bin/job queue` to verify the application's queue. The queue can reconcile old jobs when state already exists.

## Start Codex from the factory folder

Open the **factory folder** in Codex so it loads the factory skill and agents. Give the session access to the application checkout as well so it can read the code and Git can register linked worktrees. Application code changes happen in the linked worktrees under the factory directory. The application's normal working tree does not receive a factory install, checks, skill files or ignore rules.

Use `$factory` to choose GitHub or disconnected mode. For GitHub, start with one labeled test issue using `$factory run <issue>`. For disconnected mode, describe the task in chat and send `/factory execute` or `$factory execute`. Verify the result is a PR or local branch for human merge.

For an existing bundled installation, finish or archive old jobs in place, then configure a fresh separate factory folder. Keep the original job files with that installation so they can still be resumed there. A separate installation with existing job state stays bound to its original application.
