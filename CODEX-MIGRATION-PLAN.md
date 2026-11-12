# Migrate Software Factory v2 to Codex

## Scope and target

Port the template in [software-factory-claude-code-v2](https://github.com/zazencodes/zazencodes-season-3/tree/main/src/software-factory-claude-code-v2) to the standalone `software-factory-codex` workspace. The source is a template inside the ZazenCodes repository. Its installer places the runtime in the root of the project that will receive factory jobs. Start Codex from that target project root so it discovers the factory skill, agent profiles and project instructions.

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
| Install instructions for `AGENTS.md` or `CLAUDE.md` | Target project `AGENTS.md` | Merge in project setup, dev-server and test instructions, and a short factory section. Keep the full workflow in the skill. |

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

At install time, use the project's CI and existing scripts as the source of truth. Record the resolved solution or project, frontend workspace, tool versions, check commands and local start commands in the target project's `AGENTS.md` and factory check entry point. If a repo has several unrelated solutions or apps and CI does not establish which to use, confirm the scope during install.

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

- Resolve the check entry point from the active OS and the project configuration. Run `factory/checks.ps1` on Windows and `factory/checks.sh` on Linux or WSL. Keep the script in the main checkout and run it from the job worktree through one shared launcher for the builder, review gate and final gate. Surface missing scripts, SDKs, package managers or unavailable feeds as setup blockers. Keep checks non-interactive and preserve tracked files, including lockfiles.
- Route UX and UI review when the job changes observable UI behavior, regardless of framework or which files changed. Backend-only jobs use the code reviewer and any applicable security reviewer. Every job still runs the repository's configured checks.
- For browser review of a mixed app, use the repository's combined launcher when it has one. When frontend and backend run separately, assign both ports per job and reviewer, and point the frontend proxy or API URL at that job's backend. Use local test configuration and clean up only those processes.

## 4. Port the runtime and preserve the GitHub contract

| File | Migration |
| --- | --- |
| `factory/bin/job` | Retain the state machine, label and comment behavior, worktrees and atomic state writes. Adapt the approval transition for a human merge. Remove Claude transcript scanning from `sync`. Make retrying a transition safe when a comment, label update or worktree creation succeeded before state was saved. Enforce single-orchestrator ownership across sessions to protect queue slot allocation and job creation. |
| `factory/bin/gate` | Keep the canonical checkout's checks, the protected-path check and `checks.md` / `merge-checks.md` with a commit ID. Require clean, matching job branch and PR state when using those results. |
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
4. **Merge and install.** In the disposable repository, verify that `APPROVE` readies a PR while leaving it open, EF Core migrations, MassTransit saga changes and authentication changes receive specific escalations, and the queue records a manual GitHub merge. Confirm that an interrupted run cannot call the legacy auto-merge path, and that a conflict, failed final gate or mismatched PR head leaves a specific human action. Update the install instructions to publish the factory files on the target base branch before running it. Keep `factory/jobs/` and `.worktrees/` out of Git, and verify that `.agents/` and `.codex/` are tracked.

5. **Linux and WSL verification.** Run the same worktree, locking and check-launcher tests on Linux and in WSL using separate checkouts. Confirm that OS detection selects Bash and that passing and failing checks produce the same job transitions as Windows.

## Disconnected intake

On first use in a chat, ask whether to check the labeled GitHub queue or work disconnected. Add `intake-conversation` to scope a local request from the conversation. The operator starts the pipeline with `/factory execute` or `$factory execute`. Create the job only at that point, storing the brief in `issue.md` and pinning the local base commit. Reuse the worktree, gates, review and approval stages. Hand off a local branch for human merge, and record completion when Git contains the gated commit.

The port lives in this workspace. Live GitHub and Linux or WSL pilots are still pending.
