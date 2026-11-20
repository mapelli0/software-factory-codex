# Install Software Factory for your Windows account

For the chat-based install, paste the [installation prompt](README.md#install-from-a-codex-chat) into any local Codex chat. Codex downloads the repository to a temporary folder, runs `python install.py`, and checks the installed skill and nine `factory-*.toml` agent profiles under the active Codex user directory. Once it finishes, open a fresh chat in an application project and enter `$factory status`.

On Windows you need Git, Python 3.11+, PowerShell 7 and Codex with custom agents. GitHub intake also uses an authenticated GitHub CLI. Disconnected operation works with local Git. Linux and WSL use Bash and separate user installations.

## Manual installation with PowerShell

If you prefer to install it yourself, run these commands from a folder where you keep source checkouts.

```powershell
git clone https://github.com/mapelli0/software-factory-codex.git
cd software-factory-codex
python install.py
```

The installer prints the absolute launcher path. It copies the skill and runtime to `skills/factory` and the nine factory-prefixed role profiles to `agents` under `CODEX_HOME` (normally `~/.codex`). It preserves unrelated skills and roles and reports a conflicting local edit before updating.

Job state, the project registry, preview port assignments, backups and dashboard state live in `%LOCALAPPDATA%\software-factory-codex` on Windows and the user's XDG data directory on Linux. Set `SOFTWARE_FACTORY_HOME` to choose a different permanent data directory outside your application checkouts. Keep that setting consistent across chats. Only portable project settings belong in Git.

## Shared folder permissions

An ordinary install or update configures write access to the shared data folder automatically when your user `config.toml` has no explicit permission settings. The installer creates a profile named `factory`, selects it as the user default, and prints the exact folder. It adds that one folder to the usual project workspace. Every chat using this profile can write there, including chats for other projects. This lets the factory update jobs and dashboard state across projects without repeated approval for those writes.

Open a **fresh chat** after installing. If needed, select **Custom (config.toml)** in the permissions control below the message box. Installation, protected Git files, and network actions such as pushing to GitHub can still require approval. Your organization's policy determines which modes are available. [Codex permission modes](https://learn.chatgpt.com/docs/permission-modes)

If the installer reports **Kept your existing** settings, you can keep using the factory with your current approvals. To grant the data folder access manually, open `config.toml` under `CODEX_HOME` (normally `~/.codex`).

- With an existing named workspace profile, add the printed **Local data** path to that profile's `workspace_roots` table. If the table already exists, add only the path line.
- With the older `sandbox_mode = "workspace-write"` setting, add the printed absolute path to the `writable_roots` list under `[sandbox_workspace_write]`. Keep any existing entries. [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- For a managed profile, ask your administrator to add the folder to the permitted workspace roots. [Codex permission profiles](https://learn.chatgpt.com/docs/permissions)

For manual setup in a config with no existing permission settings, the Windows example below shows the complete addition. Place `default_permissions` above the first table and add the two tables at the end of the file. For a custom location or Linux, use the path printed by the installer with forward slashes.

```toml
default_permissions = "factory"

[permissions.factory]
extends = ":workspace"

[permissions.factory.workspace_roots]
"~/AppData/Local/software-factory-codex" = true
```

Run `python install.py --skip-permissions` to install or update just the factory. To undo an automatic setup, remove the installer-added `default_permissions = "factory"` line and both `permissions.factory` tables, then open a fresh chat. Use `--skip-permissions` on future updates to keep that choice.

### If a run keeps asking for approval

In the affected project chat, enter **`$factory doctor`**. For a job already in progress, use **`$factory doctor <job-id>`** with the ID from the board. The command prints the installed version and data path and tries a temporary file write with that chat's permissions. The job-specific check also tests its actual artifact folder. Run it with ordinary permissions so the result reflects what the factory can do during a job.

- **Write denied.** Compare the printed **Factory data** path with the enabled folder in your permission profile. Check any `SOFTWARE_FACTORY_HOME` override on this machine. Select **Custom (config.toml)** in the parent project chat if you use the installer profile. After changing a configuration file, open a fresh chat and repeat the check. Workers inherit the parent's permission mode. [Codex subagent permissions](https://learn.chatgpt.com/docs/agent-configuration/subagents#approvals-and-sandbox-controls)
- **Write check passed.** The parent can save the intake report in the tested folder. Starting specification automatically assigns reviewers according to the project's risk and surface rules. Creating the linked worktree also writes branch and worktree metadata under the application's `.git` folder. Codex can still request approval for this Git operation. [Codex permission profiles](https://learn.chatgpt.com/docs/permissions)

If you also want Codex to review eligible approval requests while using the factory profile, you can set the top-level `approvals_reviewer = "auto_review"` in your user config with an `on-request` or supported granular approval policy. This is an account-wide choice for chats using that config. Availability depends on your organization's settings. [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)

## Update an existing global installation

Finish active factory runs and stop the shared dashboard. Paste the same installation prompt into Codex to fetch and install the current version. For a manual update from an existing source checkout, run `git fetch origin --prune`, `git switch master`, `git pull --ff-only`, and `python install.py`. Open a fresh project chat after the update. The next run starts the updated board.

## Open an application

Open the application in Codex and invoke `$factory`. Its Git checkout needs a committed HEAD. The factory resolves subfolders and linked worktrees to the primary checkout and records a project ID in local Git configuration. Use `$factory status` to see the actual project, runtime version and jobs. Codex may ask for approval to record the project ID in Git. Use the global launcher's `--project "<checkout>"` option if your chat has several project folders.

The factory asks whether to check GitHub for labeled issues or work disconnected. In a disconnected chat, describe the request and send `/factory execute` or `$factory execute` when the brief is ready. When execution starts or resumes, the factory posts the clickable dashboard address in chat before dispatching work. Enter `$factory dashboard` to show it again during a run. Each project has its own run owner and job limit. Waiting for clarification or a human merge frees a slot.

## Configure validation and parallelism

Commit `.factory/project.json` in the application to share settings across computers. An application can inherit the defaults, including three active jobs. Configure its actual checks before the first build. The bundled placeholder reports a setup failure until checks are supplied. Use the application's `AGENTS.md` for setup instructions, SDK and package manager versions, and preview guidance. The factory also accepts migrated project notes in its local data directory.

This example gives a C# service two slots and runs its existing CI scripts. Paths are relative to the application root. Commit the scripts before running preflight.

```json
{
  "name": "Orders API",
  "concurrency": 2,
  "base_branch": "main",
  "checks": {
    "windows": { "shell": "pwsh", "script": "ci/check.ps1" },
    "linux": { "shell": "bash", "script": "ci/check.sh" }
  }
}
```

A platform can instead specify `"commands": [["dotnet", "test", "Orders.sln"], ["npm", "--prefix", "web", "run", "check"]]` inside its check definition. Each inner array is one executable and its arguments. The first failure stops the gate. Use the project's normal C# or React tooling and configure `protected_paths` for dependent validation files such as a shared CI helper or the frontend package scripts. A new job records its validation rules from the committed base. Project scripts run at their original paths, so PowerShell scripts can use $PSScriptRoot. Its project settings and declared check scripts are protected during review. Project overrides take precedence over migrated local settings and then the shared defaults.

In PowerShell, use the launcher path printed by the installer. These commands work from the application folder.

```powershell
$codexDirectory = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
$factoryLauncher = Join-Path $codexDirectory 'skills/factory/factory.py'
python $factoryLauncher gate --preflight
python $factoryLauncher status
python $factoryLauncher dashboard start
```

## Migrate an existing installation

For maintenance of an older per-project installation, its [original setup guide](https://github.com/mapelli0/software-factory-codex/blob/11177bb7ab5787d66a78497dbb38f35ddc8ac4e4/INSTALL.md) is available.

At setup, ask which folders to check for legacy installations. Use `python install.py --scan "<parent folder>"` to inventory them on this computer. You can also run `python $factoryLauncher discover --remember "<folder>"` later. Review inaccessible or ambiguous locations separately.

1. Open the application and enter `$factory cleanup`. It checks the current project and known installations bound to it. If the old skill handles the command, use `python $factoryLauncher cleanup` directly. For an external factory the inventory has not seen, add `--legacy "<old factory folder>"`.
2. Read the paths, completed jobs and custom settings in the preview. Finish pending jobs and close old workers before cutover. A stale owner or a linked worktree needs attention in the old installation. Keep an independent copy of any customized legacy file flagged for review.
3. After approving the preview, Codex runs `cleanup --apply --expect <preview-id>` with the same project and legacy folder. It backs up old files, imports and verifies completed history, preserves custom checks and notes, runs project preflight, and retires confirmed files. It lists mixed shared files that need manual review. Backups are private and stay on this computer. An interrupted migration can resume with the same command.
4. Review and commit tracked removals in the affected repository so future checkouts receive the cleanup. Open a fresh chat, use `$factory status` to verify the global runtime, and run `$factory cleanup` again for **Already clean**. Use the project filter on the shared board to inspect imported jobs. To restore a stopped installation, first stop global work for that project, then use the reported backup and its relative-path manifest to restore the original files. Keep one active factory per project.

The dashboard listens on loopback, stays up after a run, and reuses its saved port when available. Run `python $factoryLauncher dashboard stop` to stop the shared board for this user.
