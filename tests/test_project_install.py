import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1]


class ProjectInstallTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.project = self.base / "project with spaces"
        self.project.mkdir()
        self.root = self.project / ".factory"
        self.bin = self.root / "factory" / "bin"
        self.entry = self.project / ".agents/skills/factory"
        self.globals = self.base / "unused global state"
        self.env = dict(os.environ, CODEX_HOME=str(self.globals / "codex"),
                        SOFTWARE_FACTORY_HOME=str(self.globals / "data"))
        self.command("git", "init")

    def command(self, *args, stdin=None, success=True, cwd=None):
        result = subprocess.run(args, input=stdin, capture_output=True, text=True, encoding="utf-8",
                                cwd=cwd or self.project, env=self.env)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result.stdout.strip()

    def commit_application(self):
        (self.project / "AGENTS.md").write_text("Application instructions\n", encoding="utf-8")
        self.command("git", "add", "AGENTS.md")
        self.command("git", "-c", "user.name=Tester", "-c", "user.email=test@example.com",
                     "-c", "commit.gpgsign=false", "commit", "-m", "Initial application")

    def install(self, *args, **kwargs):
        return self.command(sys.executable, SOURCE / "install.py", *(args or (self.project,)), **kwargs)

    def test_install_and_disconnected_worktree(self):
        self.commit_application()
        self.install()
        self.assertEqual(set(p.name for p in self.project.iterdir()), {".git", ".agents", ".factory", "AGENTS.md"})
        manifest = (self.entry / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("\nname: factory\n", manifest)
        self.assertIn(".factory/.agents/skills/factory/SKILL.md", manifest)
        self.assertTrue((self.root / ".agents/skills/factory/SKILL.md").is_file())
        self.assertEqual(len(list((self.root / ".codex/agents").glob("*.toml"))), 9)
        self.assertEqual(self.command(sys.executable, self.bin / "job", "project", cwd=self.base),
                         str(self.project))
        job = [sys.executable, self.bin / "job"]
        self.command("git", "branch", "factory/001-test-install")
        self.command("git", "update-ref", "refs/remotes/origin/factory/002-prior-job", "HEAD")
        token = self.command(*job, "claim")
        claimed = [*job, "--run", token]
        job_id = self.command(*claimed, "create-local", "Test install", stdin="Build a test feature.")
        self.assertEqual(job_id, "003-test-install")
        folder = self.root / "factory" / "jobs" / job_id
        (folder / "intake.md").write_text("DECISION: ACCEPT\nRISK: low\nSURFACES: none\n\nProceed.\n")
        self.command(sys.executable, self.bin / "route", "--run", token, job_id)
        self.command(*claimed, "advance", job_id, "spec")
        state = json.loads((folder / "job.json").read_text())
        worktree = self.root / ".worktrees" / job_id
        self.assertEqual(Path(state["worktree"]), worktree)
        self.assertEqual(Path(state["project_checkout"]), self.project)
        self.assertTrue((worktree / "AGENTS.md").is_file())
        (folder / "spec.md").write_text("Exercise the gate.\n")
        self.command(*claimed, "advance", job_id, "build")
        # Configure a local check that verifies its working directory is the application worktree.
        (self.root / "factory/checks.ps1").write_text(
            "if (-not (Test-Path 'AGENTS.md')) { exit 1 }\n", encoding="utf-8")
        (self.root / "factory/checks.sh").write_bytes(b"test -f AGENTS.md\n")
        self.assertIn("GATE: PASS", self.command(sys.executable, self.bin / "gate", job_id, cwd=self.base))
        self.command(*claimed, "release")
        self.assertEqual(self.command("git", "status", "--porcelain"), "")
        self.assertFalse(self.globals.exists())

    def test_second_install_preserves_configuration_and_repairs_missing_files(self):
        self.commit_application()
        self.install()
        config = self.root / "factory/config.json"
        config.write_text('{"local": true}')
        (self.bin / "gate").unlink()
        self.install()
        self.assertEqual(config.read_text(), '{"local": true}')
        self.assertTrue((self.bin / "gate").is_file())

    def test_upgrade_registers_skill_and_repairs_missing_entry_files(self):
        self.commit_application()
        self.install()
        skill = self.entry / "SKILL.md"
        ignore = self.entry / ".gitignore"
        for file in (skill, ignore):
            file.unlink()
        self.entry.rmdir()  # The previous installer only wrote the nested workflow.
        history = self.root / "factory/jobs/001-existing/job.json"
        history.parent.mkdir(parents=True)
        history.write_bytes(b"preserved job")
        other_skill = self.entry.parent / "another/SKILL.md"
        other_skill.parent.mkdir()
        other_skill.write_bytes(b"existing project skill")
        self.install()
        for file in (skill, ignore):
            original = file.read_bytes()
            file.unlink()
            self.install()
            self.assertEqual(file.read_bytes(), original)
        self.assertEqual(history.read_bytes(), b"preserved job")
        self.assertEqual(other_skill.read_bytes(), b"existing project skill")
        self.assertEqual(self.command("git", "status", "--porcelain", "--untracked-files=all"),
                         "?? .agents/skills/another/SKILL.md")

    def test_project_skill_collision_preserves_existing_files(self):
        self.commit_application()
        self.entry.mkdir(parents=True)
        skill = self.entry / "SKILL.md"
        skill.write_bytes(b"own $factory")
        self.install(success=False)
        self.assertEqual(skill.read_bytes(), b"own $factory")
        self.assertFalse(self.root.exists())
        self.assertFalse((self.entry / ".gitignore").exists())

    def test_reject_linked_project_skills_parent(self):
        self.commit_application()
        outside = self.base / "shared skills"
        outside.mkdir()
        try:
            (self.project / ".agents").symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"creating symlinks requires permission on this machine: {error}")
        self.install(success=False)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse(self.root.exists())

    def test_invalid_projects_and_existing_directory(self):
        self.install(success=False)
        self.assertFalse(self.root.exists())
        self.commit_application()
        subfolder = self.project / "nested"
        subfolder.mkdir()
        self.install(subfolder, success=False)
        self.assertFalse((subfolder / ".factory").exists())
        self.root.mkdir()
        personal = self.root / "project.json"
        personal.write_text("{}")
        self.install(success=False)
        self.assertEqual(list(self.root.iterdir()), [personal])

    def test_linked_destination_is_rejected(self):
        self.commit_application()
        outside = self.base / "outside"
        outside.mkdir()
        try:
            self.root.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"creating symlinks requires permission on this machine: {error}")
        self.install(success=False)
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
