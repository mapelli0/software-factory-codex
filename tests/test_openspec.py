"""Exercise the installed factory against a real, disposable OpenSpec planning root."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1]
OPENSPEC = shutil.which("openspec.cmd" if os.name == "nt" else "openspec")


@unittest.skipUnless(OPENSPEC, "OpenSpec CLI is optional for other factory workflows")
class OpenSpecIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.planning = Path(temporary.name).resolve()
        self.app = self.planning / "Application"
        self.app.mkdir()
        self.factory = self.app / ".factory/factory"
        self.bin = self.factory / "bin"
        self.change = self.planning / "openspec/changes/add-export"
        self.env = dict(os.environ, OPENSPEC_TELEMETRY="0")
        self.write(self.planning / "openspec/config.yaml", "schema: spec-driven\n")
        self.write(self.change / "proposal.md", "## Why\nAllow a CSV download.\n")
        self.write(self.change / "design.md", "Use the built-in CSV writer.\n")
        self.write(self.change / "specs/export/spec.md",
                   "## ADDED Requirements\n### Requirement: Export\nUsers SHALL export data.\n"
                   "#### Scenario: Download\n- **WHEN** requested\n- **THEN** return CSV\n")
        self.tasks = self.change / "tasks.md"
        self.checklist = "## Export\n- [x] 1.1 Select CSV\n- [ ] 1.2 Build CSV\n"
        self.write(self.tasks, self.checklist)
        self.write(self.change.parent / "draft/proposal.md", "## Why\nA draft.\n")
        self.write(self.change.parent / "already-done/tasks.md", "- [x] Already finished\n")
        self.write(self.change.parent / "archive/2026-01-01-previous/tasks.md", "- [x] Done\n")
        self.command("git", "init", "-q")
        self.command("git", "config", "user.name", "Fixture")
        self.command("git", "config", "user.email", "fixture@example.test")
        self.command("git", "config", "commit.gpgsign", "false")
        self.command("git", "commit", "--allow-empty", "-m", "Initial revision")
        self.command(sys.executable, SOURCE / "install.py", self.app)

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def command(self, *args, cwd=None, brief="", success=True):
        result = subprocess.run(list(map(str, args)), cwd=cwd or self.app, env=self.env,
                                input=brief, capture_output=True, encoding="utf-8")
        if success:
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result.stdout.strip()

    def job(self, *args, **kwargs):
        return self.command(sys.executable, self.bin / "job", *args, **kwargs)

    def test_reads_drafts_and_only_creates_jobs_for_implementable_selections(self):
        listing = json.loads(self.job("openspec-list"))
        self.assertEqual(Path(listing["root"]), self.planning)
        self.assertEqual({change["name"] for change in listing["changes"]}, {"draft", "add-export"})
        draft = json.loads(self.job("openspec-show", "draft"))
        self.assertIn("proposal.md", draft["documents"])
        self.assertEqual(draft["state"], "blocked")
        self.job("create-openspec", "draft", success=False)
        self.job("openspec-show", "../outside", success=False)
        self.job("openspec-show", "missing-change", success=False)
        self.assertFalse(list((self.factory / "jobs").glob("*/job.json")))
        self.assertEqual(self.tasks.read_text(), self.checklist)

    def test_selected_parent_plan_survives_intake_review_and_merge(self):
        self.write(self.factory / "checks.ps1", "if (-not (Test-Path 'export.csv')) { exit 1 }\n")
        self.write(self.factory / "checks.sh", "test -f export.csv\n")
        inspected = json.loads(self.job("openspec-show", "add-export"))
        self.job("create-openspec", "add-export", "0" * 64, success=False)
        self.assertFalse(list((self.factory / "jobs").glob("*/job.json")))
        job_id = self.job("create-openspec", "add-export", inspected["scope_digest"], brief="Use CSV.\n")
        self.assertEqual(self.job("create-openspec", "add-export"), job_id)
        folder = self.factory / "jobs" / job_id
        snapshot = json.loads((folder / "openspec.json").read_text(encoding="utf-8"))
        self.assertEqual(snapshot["documents"]["tasks.md"], self.tasks.read_bytes().decode("utf-8"))
        self.assertIn("specs/export/spec.md", snapshot["documents"])
        listing = json.loads(self.job("openspec-list"))
        chosen = next(c for c in listing["changes"] if c["name"] == "add-export")
        self.assertEqual(chosen["job_id"], job_id)
        self.write(folder / "intake.md", "DECISION: NEEDS-INFO\nRISK: low\nSURFACES: none\n\nHeader?\n")
        self.job("advance", job_id, "needs-info")
        self.job("clarify-local", job_id, brief="Include a header.")
        self.assertIn("Include a header.", (folder / "issue.md").read_text())
        self.write(folder / "intake.md", "DECISION: ACCEPT\nRISK: low\nSURFACES: none\n\nUse CSV.\n")
        self.command(sys.executable, self.bin / "route", job_id)
        self.job("advance", job_id, "spec")
        self.write(folder / "spec.md", "Export CSV with a header for task 1.2.\n")
        self.job("advance", job_id, "build")
        worktree = self.app / ".factory/.worktrees" / job_id
        self.write(worktree / "export.csv", "name\n")
        self.command("git", "add", "export.csv", cwd=worktree)
        self.command("git", "commit", "-m", "Implement CSV", cwd=worktree)
        reviewed = self.command("git", "rev-parse", "HEAD", cwd=worktree)
        self.write(folder / "build.md", "STATUS: READY\n\nTask 1.2 exports the name header.\n")
        self.job("advance", job_id, "gate")
        self.command(sys.executable, self.bin / "gate", job_id)
        self.job("advance", job_id, "review")
        self.write(folder / "round-1/review-code.md", f"VERDICT: PASS\nCOMMIT: {reviewed}\n")
        self.job("advance", job_id, "approve")
        self.write(folder / "decision.md", "APPROVE\n\nVerified the CSV feature.\n")
        self.job("ready", job_id)
        self.job("openspec-closeout", job_id, success=False)
        self.assertEqual(self.tasks.read_text(), self.checklist)
        self.command("git", "merge", "--ff-only", reviewed)
        closeout = json.loads(self.job("openspec-closeout", job_id))
        self.assertFalse(closeout["already_complete"])
        self.assertEqual(closeout["tracking_file"], "tasks.md")
        self.job("complete-local", job_id, success=False)
        self.job("advance", job_id, "merged", success=False)
        # Simulate the project apply skill reconciling its authoritative checklist.
        complete = self.checklist.replace("[ ]", "[x]")
        self.write(self.tasks, complete + "- [x] 1.3 An unreviewed new task\n")
        self.job("openspec-closeout", job_id, success=False)
        self.job("complete-local", job_id, success=False)
        self.write(self.tasks, complete)
        self.assertTrue(json.loads(self.job("openspec-closeout", job_id))["already_complete"])
        self.assertIn("add-export", [c["name"] for c in json.loads(self.job("openspec-list"))["changes"]])
        self.job("complete-local", job_id)
        self.job("complete-local", job_id)
        self.assertEqual([c["name"] for c in json.loads(self.job("openspec-list"))["changes"]], ["draft"])
        self.assertEqual(json.loads((folder / "job.json").read_text())["stage"], "merged")
        self.assertEqual(self.tasks.read_text(), complete)
        self.assertTrue((self.change.parent / "draft/proposal.md").is_file())


if __name__ == "__main__":
    unittest.main()
