# Factory design

Codex discovers `.agents/skills/factory/SKILL.md` and the nine custom agents under `.codex/agents/`. The parent supervises the queue and agents. It works from the project root and keeps job state in `factory/jobs/`. Each accepted request gets a dedicated worktree. GitHub jobs get one PR and disconnected jobs retain a local branch.

| Component | Responsibility |
| --- | --- |
| `factory/bin/job` | Own job state, enforce legal stage transitions, coordinate worktrees and GitHub handoffs, and reconcile manual merges. |
| `factory/bin/route` | Select code review and the UX, UI or security lenses based on intake risk and surfaces. A `default` model entry uses the client's defaults. |
| `factory/bin/gate` | Run the configured checks from the worktree and record the result, commit and merge base. Verify protected paths. |
| `factory/bin/runtime.py` | Select PowerShell and Windows file locking, or Bash and POSIX file locking. |
| `factory/dashboard.html` | Show job state, review rounds, handoffs and job artifacts. |

## Workflow

On initialization the operator chooses the GitHub queue or disconnected conversation intake. The latter drafts the brief in the conversation and waits for `/factory execute` or `$factory execute`. At execute, the job stores the brief as `issue.md` and pins the main checkout's committed HEAD as its base. Intake accepts, rejects or asks for information in either mode. GitHub builds push a draft PR and disconnected builds commit locally. The gate verifies the worktree commit before dispatching reviewers. Review artifacts carry the commit they reviewed. Failing checks or reviews return the job to the builder up to its round limit. When the approver records APPROVE, `job ready` runs the final gate. In GitHub mode it also synchronizes with the base and verifies the reviewed diff before the PR is marked ready. Disconnected mode reports the gated local branch and commit. The operator merges using the applicable Git workflow. A job may also wait for an explicit operator decision.

## State and recovery

Only `job` writes `job.json`. It serializes state commands using an OS file lock and replaces the saved JSON atomically. `job claim` reserves the checkout for an orchestrator. A resumed run reuses valid artifacts and releases its claim when it finishes. The queue records manually merged PRs. The original transcripts are unnecessary for progress. Existing historical cost figures remain visible. New jobs show unavailable cost until usage accounting is configured.
