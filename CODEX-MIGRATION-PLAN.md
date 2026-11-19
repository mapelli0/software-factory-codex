# Migrate Software Factory v2 to Codex

## Scope and target

Port the template in [software-factory-claude-code-v2](https://github.com/zazencodes/zazencodes-season-3/tree/main/src/software-factory-claude-code-v2) to the standalone `software-factory-codex` workspace. The source is a template inside the ZazenCodes repository. The installer defaults to the current local Codex project's primary folder when suitable and asks for the application checkout if needed. Start Codex from that factory directory so it discovers the skill and agent profiles. The factory stores its binding locally and keeps its tools, checks, job state and worktrees outside the application checkout.

Treat C#/.NET as the primary backend stack and React as the first supported UI stack. Cover backend-only, UI-only and mixed repositories, with the same install contract for other UI stacks.

Build and pilot the first release on native Windows using PowerShell. Keep one factory implementation that selects its check runner and file locking from the OS of the running Python process. A run started in WSL uses the Linux path. Validate Linux and WSL separately before advertising support.

The workflow starts with an explicit user request. It takes open GitHub issues labeled `factory` through intake, risk routing, a dedicated worktree, specification, build, deterministic checks, parallel reviews and a final decision. Keep one branch and PR per issue, the three-round default, the three job slots and file-based resume. Start the pilot with one job slot. The first release requires a human to merge every PR on GitHub.

This plan incorporates the earlier discussion about Codex orchestration, merge policy, .NET checks and licensing. [Port Factory To Codex](https://chatgpt.com/share/6af58922-df8c-83ed-9538-7cb7cba15e59)

## 1. Port the skill and all eight roles

| Claude source | Codex destination | Work |
| --- | --- | --- |
| `.claude/skills/factory/SKILL.md` | `.agents/skills/factory/SKILL.md` | Use `$factory run`, `$factory run <issue>` and `$factory <request>` for status, questions, feedback, rejection and new issues. Keep the parent as the sole orchestrator and `job` as the sole writer of `job.json`. |
| `.claude/agents/intake.md` | `.codex/agents/intake.toml` | Preserve ACCEPT, NEEDS-INFO and REJECT, rescoped scope, risk and surfaces. Disable shell in this profile where supported and verify it can still read the issue and write `intake.md`. |
| `.claude/agents/spec-writer.md` | `.codex/agents/spec-writer.toml` | Use intake's accepted scope to produce `spec.md` with observable acceptance criteria. |
| `.claude/agents/builder.md` | `.codex/agents/builder.toml` | Edit and validate the assigned worktree, commit and push the job branch, open or reuse the draft PR and write `build.md`. |
| `.claude/agents/reviewer-code.md` | `.codex/agents/reviewer-code.toml` | Check correctness, scope, conventions and tests. Write `round-N/review-code.md`. |
| `.claude/agents/reviewer-security.md` | `.codex/agents/reviewer-security.toml` | Review the generated changes defensively for issues such as access control, unsafe input handling and data exposure. Write `round-N/review-security.md`. |
| `.claude/agents/reviewer-ux.md` | `.codex/agents/reviewer-ux.toml` | Check user flows, states, accessibility and mobile behavior. Write `round-N/review-ux.md`. |
| `.claude/agents/reviewer-ui.md` | `.codex/agents/reviewer-ui.toml` | Check visual consistency at desktop and mobile widths. Write `round-N/review-ui.md`. |
| `.claude/agents/approver.md` | `.codex/agents/approver.toml` | Preserve APPROVE and ESCALATE in `decision.md`. APPROVE sends the PR to the operator for merge. ESCALATE records what the operator must review or decide. Add EF Core migrations, MassTransit saga changes and authentication to the explicit escalation criteria. |
| Install instructions for `AGENTS.md` or `CLAUDE.md` | Factory `PROJECT.local.md` | Record any setup, dev-server or test instructions needed beyond the application's existing guidance. Keep the full workflow in the skill. |

Translate role frontmatter to TOML fields `name`, `description` and `developer_instructions`. Preserve artifact filenames, first-line verdicts and summary sections because the Python scripts and dashboard parse them. Codex subagents inherit the parent session's permissions and MCP connections. Verify capability restrictions on the chosen client. If a target requires enforced read-only access for a role, run that role in a separate read-only invocation and have the parent validate and save its artifact. [Build skills](https://learn.chatgpt.com/docs/build-skills) · [Custom instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md) · [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)

## 2. Adapt orchestration, models and browser checks

Use the Codex skill and native subagents for the first release. Keep Python responsible for state transitions, worktrees and quality gates, and keep the existing dashboard. Verify subagent discovery, completion and recovery on the Codex version installed in the pilot environment.

For a future unattended Jenkins job or Azure VM deployment, evaluate a Python orchestrator that runs each role through `codex exec` or the Codex SDK. Reuse the role instructions and job artifacts. Give the runner explicit ownership of timeouts, retries, concurrency and recovery, with the same human merge policy. [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) · [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)

- Replace Claude's background completion callbacks with Codex spawn and wait behavior. Keep the parent turn active until the selected jobs reach `merged`, `rejected`, `needs-info` or `needs-human`. Track live agent handles by job, role and round. Release completed handles and run the queue again when a job frees a slot.
- Resume from disk after a restart. Start a fresh builder with `build.md`, Git history and the previous round's findings when a live builder handle is unavailable. During review, reuse valid artifacts for the current commit and rerun missing or invalid reviews. Advance only when every routed reviewer has returned a valid verdict. Reconcile manually merged PRs and stop any workers that still belong to those jobs.
- Keep the current risk and surface routing. Code review always runs. UI changes add UX and UI, and security changes add the defensive security reviewer. Replace the Claude aliases with configurable Codex models and reasoning levels. Use the signed-in account's available models. A custom role's fixed model overrides a spawn-time choice, so leave the routed role's model unset if the client supports spawn overrides. Otherwise, use separate profiles for the routed model choices and let `route` select them. Verify the selected model for low- and higher-risk code review. Three simultaneous jobs can reach 12 reviewer threads. Bound scheduling by both job slots and the configured agent limit. [Model precedence and agent limits](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- Remove the Claude builder hook and the `gate --hook` transcript reader. Keep the builder's explicit check run and the orchestrator's mandatory gate. If a builder completion reminder is needed later, implement it as a trusted Codex `SubagentStop` hook using explicit job metadata. [Codex hooks](https://learn.chatgpt.com/docs/hooks#subagentstop)
- Keep the existing per-job ports and distinct browser sessions for builder, UX and UI. Verify the configured browser tool on native Windows, using the existing `agent-browser` integration if available. Track the browser sessions and dev-server processes each worker starts. Use that ownership to clean them up on completion or interruption. Record desktop and mobile evidence, and report an unavailable browser check before accepting a user-facing change.

## 3. Support C#/.NET, React and other UI stacks

At install time, use the project's CI and existing scripts as the source of truth. Record the resolved solution or project, frontend workspace, tool versions, check commands and local start commands in the factory's local project notes and check entry point. If a repo has several unrelated solutions or apps and CI does not establish which to use, confirm the scope during install.

| Project type | Default validation |
| --- | --- |
| C#/.NET | Identify the applicable `.sln`, `.slnx` or `.csproj`. Honor `global.json`, project target frameworks, NuGet configuration and the existing test runner. Use CI's restore, build and test steps, or configure `dotnet restore`, `dotnet build` and `dotnet test` as appropriate when CI is absent. Use the repo's MSBuild commands and Windows tooling for legacy or Windows-specific projects that require them. |
| React | Use the repository's Node version, package manager, lockfile and workspace. Restore dependencies with the existing locked install command, such as `npm ci` for an npm lockfile. Run the configured lint, typecheck, non-watch tests and production build where present. Discover the development and test commands from the project so React works with the existing build system. |
| ASP.NET Core + React | Run both sets of checks in the same job. Use the existing combined CI command when it already covers both. For a feature that crosses the API/UI boundary, verify the changed behavior through the running app and exercise the API contract with the project's existing tests. |
| Other UI | Use the same project-defined install, build, test and preview commands. Reuse the browser reviewers for browser apps. For desktop UI, document the project's local preview or UI test steps and escalate if the required visual check cannot be performed. |

For an SDK-style .NET solution whose CI does not already prescribe a sequence, use this Release-mode baseline from the solution directory. Pass the chosen solution or project explicitly if discovery is ambiguous. Add existing architecture, formatting or integration checks where the project uses them. [.NET SDK selection](https://learn.microsoft.com/en-us/dotnet/core/tools/global-json) · [.NET test runners](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-test) · [npm clean installs](https://docs.npmjs.com/cli/v11/commands/npm-ci/)

```text
dotnet restore
dotnet build -c Release --no-restore
dotnet test -c Release --no-restore
```

- Resolve the check entry point from the active OS and the project configuration. Run `factory/checks.ps1` on Windows and `factory/checks.sh` on Linux or WSL. Keep the script in the factory directory and run it from the job worktree through one shared launcher for the builder, review gate and final gate. Surface missing scripts, SDKs, package managers or unavailable feeds as setup blockers. Keep checks non-interactive and preserve tracked files, including lockfiles.
- Route UX and UI review when the job changes observable UI behavior, regardless of framework or which files changed. Backend-only jobs use the code reviewer and any applicable security reviewer. Every job still runs the repository's configured checks.
- For browser review of a mixed app, use the repository's combined launcher when it has one. When frontend and backend run separately, assign both ports per job and reviewer, and point the frontend proxy or API URL at that job's backend. Use local test configuration and clean up only those processes.

## 4. Port the runtime and preserve the GitHub contract

| File | Migration |
| --- | --- |
| `factory/bin/job` | Retain the state machine, label and comment behavior, worktrees and atomic state writes. Adapt the approval transition for a human merge. Remove Claude transcript scanning from `sync`. Make retrying a transition safe when a comment, label update or worktree creation succeeded before state was saved. Enforce single-orchestrator ownership across sessions to protect queue slot allocation and job creation. |
| `factory/bin/gate` | Keep the factory's checks, the protected-path check and `checks.md` / `merge-checks.md` with a commit ID. Require clean, matching job branch and PR state when using those results. |
| `factory/bin/route` and `factory/config.json` | Retain the risk/surface tables, label names, round limit and ports. Accept the legacy merge-method setting for config compatibility. Validate the new Codex route values and translate old Claude route values on resume if importing active jobs. |
| `factory/checks.ps1` and `factory/checks.sh` | Add the native Windows entry point and retain the Bash entry point for Linux or WSL. Configure the target project's non-interactive .NET and UI validation commands. Protect both entry points and their launcher from job-branch changes. |
| `factory/dashboard.html` | Retain the job board, stage names, round verdicts, file drawer and issue/PR links. Show whether a job is waiting for routine human merge or for a specific decision. Change command hints and Claude model labels. Serve the job board on loopback since it displays issue and check contents. |
| `README.md`, `INSTALL.md`, `DESIGN.md`, `LICENSE`, `docs/assets/` and `examples/jobs/` | Update the setup, invocation, routing, runtime and usage documentation. Preserve the upstream GPLv3 license and attribution for copied material. If the port will be distributed as part of proprietary tooling, review the license terms and the author's commercial licensing option before distribution. Carry over the four historical jobs as fixtures, with the cryptojacking request used only to confirm rejection at intake. |

**Platform selection.** Detect the OS once at startup. Use native PowerShell and a Windows-compatible file lock on Windows. Use Bash and the existing `fcntl` lock on Linux, including WSL. Give both implementations the same lock and atomic state-write behavior. Select and verify the interpreter during install, then launch checks with separate command arguments and an explicit worktree directory so paths with spaces work. Run child Python scripts with the current Python executable. Treat a missing configured runner or a nonzero command exit as a failure. In PowerShell, explicitly propagate failures from native commands such as `dotnet` and the frontend package manager.

**Windows pilot setup.** Run Codex, Git, Python, GitHub CLI, .NET, Node and the browser tooling as native Windows programs. Keep each run's tools, checkout and job state in that environment. Verify the repo's requested SDKs and tooling before the pilot. PowerShell 7, Git, `dotnet` and Node are on the current Windows path. GitHub CLI and `agent-browser` did not resolve in the current shell.

**GitHub.** Retain the label requirement and keep issue text and comments quoted as data in `issue.md`. Validate the job branch, base, PR and checked commit before approving. Tie review results to the checked commit. After syncing with the base, run the final gate and verify the published PR head matches the gated commit before declaring it ready. If syncing changes the reviewed diff, send it through review again. A stale head, conflict or failed final check gets a specific handoff. GitHub branch protection and required checks govern the human merge. Keep a single set of job state files on cutover. If importing active jobs, back them up and reconcile worktree paths, branches and PRs. For a job left in `merging`, record an existing GitHub merge or hand the open PR to the operator.

**Human merge.** Route `APPROVE` to `needs-human` with a ready PR and a clear merge handoff. Route `ESCALATE` to the same stage with the decision or verification needed. Retain the original verdict in the artifact and display the distinction in the dashboard. The first release disables the automated merge command and its transition. Mark a job `merged` only after GitHub reports the human merge. Treat auto-merge as a separate future opt-in decision.

**Usage.** Replace the Claude transcript and price table together. Let the dashboard show unknown usage as unavailable and continue to render historical cost figures. If per-job accounting is required for parity, capture supported events from per-role `codex exec --json` runs, keyed by job, role, round and invocation. Verify actual model attribution before displaying estimates. Unknown usage or prices must never stop state transitions. [Non-interactive mode and JSON events](https://learn.chatgpt.com/docs/non-interactive-mode#make-output-machine-readable)

## 5. Verify and roll out

1. **Native Windows verification.** From a clean Windows checkout, check that Codex discovers the skill and all eight profiles, routes each risk/surface combination, writes the existing artifact formats, and resolves the intended worktree even when a path contains spaces. Verify PowerShell propagates failed tool exits, locks prevent concurrent state corruption, and browser and dev-server cleanup works. Run the target's real checks from a fresh worktree. Include a C#-only job, a React-only job, and a mixed ASP.NET Core + React job. Confirm that a .NET test failure and a React check failure each block progression, and that the mixed app's browser review uses its own backend and frontend ports. Verify the dashboard against the existing fixtures and a record with unavailable usage.
2. **Disposable GitHub pilot on Windows.** With one slot, take a small labeled C# issue through a passing gate, one code review and a draft PR. Then run a React issue that exercises the UI and UX reviews. Also test an unlabeled issue, a needs-info reply, a rejected issue, UI and security routing, a failed gate that skips review, a CHANGES verdict, round exhaustion, human feedback and a manual merge. Confirm the original checkout stays clean and one issue gets one PR.
3. **Recovery and parallelism.** Interrupt a build and a partly completed review, then resume in a fresh chat. Confirm the completed work is reused appropriately, comments and PRs are not duplicated, and stale verdicts do not advance the job. Run multiple jobs and verify job slots, agent slots, locks and browser ports stay independent.
4. **Merge and install.** In the disposable repository, verify that `APPROVE` readies a PR while leaving it open, EF Core migrations, MassTransit saga changes and authentication changes receive specific escalations, and the queue records a manual GitHub merge. Confirm that an interrupted run cannot call the legacy auto-merge path, and that a conflict, failed final gate or mismatched PR head leaves a specific human action. Verify the standalone installation can run against an application branch with no factory files. Keep `factory/jobs/` and `.worktrees/` out of Git, and verify that `.agents/` and `.codex/` are tracked.

5. **Linux and WSL verification.** Run the same worktree, locking and check-launcher tests on Linux and in WSL using separate checkouts. Confirm that OS detection selects Bash and that passing and failing checks produce the same job transitions as Windows.

## Disconnected intake

On first use in a chat, ask whether to check the labeled GitHub queue or work disconnected. Add `intake-conversation` to scope a local request from the conversation. The operator starts the pipeline with `/factory execute` or `$factory execute`. Create the job only at that point, storing the brief in `issue.md` and pinning the local base commit. Reuse the worktree, gates, review and approval stages. Hand off a local branch for human merge, and record completion when Git contains the gated commit.

The port lives in this workspace. Live GitHub and Linux or WSL pilots are still pending.

## Proposed next release — one factory for all local projects

Install the factory once per user on each computer. Open an application in Codex and invoke `$factory` there. The first execution starts one live dashboard. Runs from other projects reuse its URL. Each chat continues to drive its selected project. Opening the board only reads local job records, so viewing all projects never starts another project's queue.

### 1. Install once and register projects on first use

Keep one versioned copy of the Python tools, default settings and dashboard outside application checkouts. The installer supplied by this repository installs the `$factory` skill and nine factory-prefixed agent roles in Codex's user-level discovery folders. Make repeat installs update only factory-owned files and preserve unrelated personal skills and agents. Test discovery from a fresh application chat on native Windows without requiring Windows symlink privileges. [Codex skill locations](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills) and [personal custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents).

On first use, resolve the application from the current Git checkout, including from a subfolder. Link related worktrees to the registered checkout. Ask which project to use when the context is ambiguous. Keep a machine-local registry mapping a stable project ID to the checkout and display name. Registration also works without a Git remote. Detect a moved checkout or a second clone and resolve its identity before starting work. Continue to ask whether to check GitHub for labeled issues or collect a disconnected brief. Only the explicit execute command starts that brief, and the operator retains the merge decision.

### 2. Keep project settings small and portable

| Where | What belongs there |
| --- | --- |
| Shared installation | Common workflow, agents, dashboard, validation runner and default settings. |
| `.factory/project.json` in the application repo | Optional, version-controlled overrides for the project name, maximum active jobs, base branch, queue labels and validation commands or existing CI script paths. Validate the file, inherit omitted settings from the shared defaults, and explain invalid values before starting work. |
| Application `AGENTS.md` | Human-readable build, test and preview guidance, such as the .NET solution, React workspace and how the UI connects to the API. Reuse existing instructions and CI scripts. |
| Local user data outside both repos | Checkout registrations, machine paths, project-specific job records and worktrees, locks, dashboard port and server state. An update of the shared tools preserves these files. |

A project can use defaults or commit just the overrides its team needs. This example gives a service two job slots.

```json
{
  "name": "Orders API",
  "concurrency": 2
}
```

Keep the gate runner in the shared install. At job creation, record the effective validation policy and the trusted base revision supplying the project's check definitions. Run these checks against the job worktree. Protect the selected check definitions so a change under review cannot weaken its own checks. Allow Windows and Linux commands to use the project's existing PowerShell, Bash, .NET or frontend scripts.

### 3. Make execution and capacity project-aware

Pass the project ID through `job`, `gate`, `route` and every worker. Scope run ownership, issue lookups, job files, Git commands and recovery to that project. Give separate projects independent owners so two chats can make progress at the same time. Use the project ID plus the existing job ID as the complete identifier, including in artifact links. Allocate preview ports across the installation so two first jobs can each start their own frontend and backend.

Apply the project's `concurrency` limit to the combined count of active GitHub and disconnected jobs. Reserve a slot under the project lock on creation or resumption. Waiting for input or human merge releases the slot. If a limit is reduced below current usage, finish active jobs and admit the next job when capacity is available. Keep three as the inherited project default. The number of reviewers that can run at once also depends on the Codex session's worker capacity.

### 4. Serve one live board

Start or reuse one loopback server under a user-wide startup lock. Save its local port for reuse across restarts when available and print the actual URL in every run. Default to **All projects**, with a project filter and active-versus-configured counts. Show the project name on every card and job detail, and qualify links with the stable project ID. For example, **Orders API · #42** and **Storefront · #42** must open different jobs. Show the waiting reason and handoff state for both intake modes. Serve only registered job artifacts and keep the board useful when a checkout is offline.

### 5. Migrate and prove the change on Windows

1. Add the migration and retirement procedure below to global setup. Run it for each existing installation and keep an inventory on this computer so interrupted migrations can resume.
2. Pilot two projects with the same issue number, different limits (two jobs and one job), and different checks. Exercise both GitHub and disconnected intake. Verify that each project reaches its own limit, an extra job waits, concurrent chats respect ownership, and waiting jobs resume only into an available slot.
3. Start both projects together. Verify one dashboard URL, correct project labels and artifact links, live updates, distinct preview ports, and independent restart and recovery. Confirm a failing .NET or React check blocks only its own job. Confirm ordinary runs add no factory runtime files to application repos.
4. Replace the per-application instructions in `README.md`, `INSTALL.md`, the skill and role prompts with the verified global workflow. Include installation from the repo, first-project registration, configuration, updates and migration. Verify the same behavior on Linux or WSL before declaring parity.

### Retire existing per-project installations

1. **Find old copies.** During global setup, offer a read-only scan of registered application checkouts and the parent folders the operator selects. Accept additional factory folders directly, since an external install can live anywhere. Look for `.factory-project.local.json` and also the combination of the local factory skill, role profiles and `factory/bin/job`. Older bundled installs can lack a binding. List each candidate, its associated project when known, and the scan roots, including any inaccessible folders. Identify the maintained source checkout, new global install, backups and ambiguous matches separately. A folder name or lone matching file is insufficient evidence for removal.
2. **Establish what must be kept.** Preview the exact paths proposed for retirement. Compare files to known factory releases and flag local edits, user-authored files, and shared settings such as `AGENTS.md`, `.codex/config.toml` and `.gitignore`. Inventory ignored job artifacts, custom checks, `PROJECT.local.md`, active owners, pending handoffs and linked Git worktrees, including dirty or unmerged work. Mark a project as pending while a run, unresolved job or worktree still needs the old install. Keep its global queue disabled until cutover so two factories cannot claim the same issue.
3. **Preserve and verify.** Once the old workers have stopped, use the old dashboard's own stop command. Save private settings and a restorable backup outside Codex project and skill discovery paths. Import project settings and completed history, compare job IDs and artifact contents, and run the global preflight with the project's checks. Preserve custom scripts before retiring their old paths. A failed or interrupted migration must leave a recoverable copy and allow a retry without duplicate jobs.
4. **Remove the local runtime.** After the operator approves the displayed changes, archive an exclusively factory-owned installation, or remove the confirmed factory files individually from a mixed project. Include the old skill, role profiles, launchers, dashboard and obsolete bindings. In shared files, remove only entries with established factory ownership and surface ambiguous edits for review. Keep application source, licenses in use and unrelated Codex settings. For tracked factory files, prepare a reviewable Git change in the affected repository so a fresh checkout also receives the cleanup. Keep backup deletion as a separate, explicit action.
5. **Prove each cutover.** From a fresh Codex chat in the application, have `$factory status` report the selected project, global runtime path and version. Check that only the global factory skill and roles are available, that the shared dashboard shows the expected history, and that the old server is stopped. Repeat discovery and check every inventoried path. Report each installation as retired, pending, or needing review, with its reason. A project passes when it resolves to the global copy and its old runtime is absent from the active locations. Provide the same read-only check after setup for other folders and computers.

Test retirement on Windows with both a separate factory folder and a bundled installation that has no binding. Include unrelated agents, a locally edited check, tracked factory files, an unfinished job, an inaccessible folder and a maintained source checkout. Verify that a second run makes no further changes after a successful cutover and that a backup can restore a stopped installation.

### Run `$factory cleanup` from an application project

Add `$factory cleanup` to the global skill and document it in `README.md` and `INSTALL.md`. It runs the same migration used during global setup, on demand for the current project. Route it directly to maintenance before intake or any GitHub queue lookup. Document how to invoke the installed global cleanup tool directly if a legacy project skill handles `$factory` in an existing chat.

1. Resolve the application from its Git root when invoked from a subfolder or linked worktree. Show the selected checkout. Inspect it for legacy factory files and consult the local migration inventory for any external installation already associated with it. Keep the scan scoped to that project. Include an external folder in the migration preview only after verifying its binding to the selected checkout.
2. If the scan completes and finds no legacy files or known bound installation, report **Already clean**, name the project and show the locations checked. This result makes no changes. Report **Needs review** when access or conflicting evidence prevents a complete check. Report **Pending** with the reason when an old run or unfinished work still needs the installation.
3. For a confirmed installation, show what will be migrated, backed up and removed. After the operator approves that preview, perform the retirement procedure above for this project, including registration if needed, import verification and a reviewable diff for tracked removals. Report **Migrated** after the follow-up scan and global runtime verification pass. An interrupted run resumes from the saved inventory.

In the Windows pilot, invoke the command from a subfolder of a project with a bundled legacy copy, migrate it, and run it again. The second run must report **Already clean** with no new diff, backup or duplicate job. Also exercise a project with unfinished work and verify that its jobs and files remain available, and that another registered project's state is untouched throughout.
