# Install Software Factory in a project

The destination is the root of the application Git checkout and must have at least one commit. On Windows, use Python 3.11+, Git, PowerShell 7 and Codex with subagents. GitHub jobs also need an authenticated GitHub CLI, a GitHub origin and the configured issue labels. Disconnected jobs use local Git.

## Install from GitHub

From a folder outside the application, clone the factory source. Replace `C:\Projects\My App` with the path to the one project you want to install into.

```powershell
git clone --depth 1 https://github.com/mapelli0/software-factory-codex.git
python .\software-factory-codex\install.py "C:\Projects\My App"
python "C:\Projects\My App\.factory\factory\bin\job" project
```

The last command prints your application's Git root. If you already have a current factory source checkout, run `python install.py "<application checkout>"` from that folder.

The installer puts the runtime, skill, nine agent profiles, configuration and checks in `My App/.factory/`. Jobs, reports, locks, dashboard state and linked working trees are created there as the factory runs. Git records its normal branches and worktree registrations in the application repository. The internal `.factory/.gitignore` ignores the whole installation. If you keep repository-wide rules, add this line to the application's `.gitignore`.

```gitignore
/.factory/
```

Rerunning the installer fills missing packaged files and preserves installed files, including customized checks. For a fresh installation, preview cleanup first. A pre-existing, unrecognized `.factory` directory needs inspection before installation.

## Configure and verify

Edit `.factory/factory/config.json` for the application's base branch, labels, concurrency and review settings. Put the same checks that the application runs in CI into `.factory/factory/checks.ps1` (Windows) or `.factory/factory/checks.sh` (Linux/WSL). The placeholder fails until configured. Checks run in the application checkout during initial preflight and in the job worktree during a build. On Windows, check `$LASTEXITCODE` after each native command. Record local setup and preview instructions in `.factory/PROJECT.local.md`.

From the **application root**, verify the selected checkout and run the checks.

```powershell
python .factory/factory/bin/job project
python .factory/factory/bin/gate --preflight
```

## Use from Codex

**Desktop, from the application root.** In a fresh project chat, enter the following. It gives Codex the local skill explicitly and keeps the application checkout, job folders and worktrees in the project workspace.

```text
Use .factory/.agents/skills/factory/SKILL.md for this project's factory. Show my factory status.
```

Continue in that chat with the factory workflow. To use the native `$factory` picker and project-local roles, start a chat with `.factory` as the working directory. Codex discovers skills from the working directory and its ancestors. An ordinary chat opened at the application root needs the explicit path above.

**CLI.** From the application root, start Codex in the installation and include the application as a writable directory for Git operations.

```powershell
codex -C .factory --add-dir (Get-Location).Path
```

Use `$factory status` for jobs, `$factory dashboard` for this project's local board, or `$factory` to choose GitHub or disconnected intake. Disconnected intake waits for `/factory execute` or `$factory execute`. GitHub and Git operations use the permissions of the current session.

## Remove old installations

From the **factory source checkout**, preview a tree of projects, then use the same path with `--apply` to carry out the listed removals.

```powershell
python cleanup.py "C:\Projects"
python cleanup.py "C:\Projects" --apply
```

Check the paths and any reported blockers. The cleaner treats a marked project-local installation as a unit, including its custom checks and job history. For older layouts it identifies factory-owned components and reports ambiguous files. Stop running workers and the project dashboard before cleanup. The preview identifies unfinished jobs and ignored files in worktrees. To discard those, add `--discard-jobs` to both the preview and apply commands. Changed or untracked work still needs to be saved. Clean worktrees are unregistered and their branches are kept. When an external factory has worktrees, choose a scan root that contains both the installation and its application. Review any tracked deletions in the application's Git diff.

An older installation may be a separate Git clone of the factory, bound to an application next to it. To remove that clone too, run the cleaner from a different source checkout. Include the clone's exact path in both calls.

```powershell
python cleanup.py "C:\Projects" --remove-legacy-clone "C:\Projects\Factory-OldApp"
python cleanup.py "C:\Projects" --remove-legacy-clone "C:\Projects\Factory-OldApp" --apply
```

This removes the named clone's Git history, local edits, tools and job records. The application's branches remain available. If the preview reports unfinished jobs or ignored worktree files, save them first or explicitly include `--discard-jobs` after reviewing the preview.

To retire the older **account-wide** release on another machine, use its installation receipt. These commands preview and then remove the verified runtime, factory agent profiles and installer-generated Codex permission settings. User data, including job records and handoffs, stays in the old data folder. Start a fresh Codex chat afterwards.

```powershell
python uninstall_global.py
python uninstall_global.py --apply
```

Use `--orphan-settings` only when you recognize an unregistered `.factory/project.json` as belonging to the old factory. For a non-default account-wide installation, pass `--codex-home` and `--data-dir` on both calls. Run `python cleanup.py --help` for project cleanup options.
