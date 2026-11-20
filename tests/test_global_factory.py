"""Windows-first integration tests. All installations, Git repositories and jobs are disposable."""

import concurrent.futures
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.request
import zipfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
LEGACY = "daec85c"


class GlobalFactoryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="global factory ")
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name).resolve()
        profile = self.temp / "profile"
        self.data = self.temp / "data"
        self.env = {**os.environ, "USERPROFILE": str(profile), "HOME": str(profile),
                    "CODEX_HOME": str(profile / ".codex"), "SOFTWARE_FACTORY_HOME": str(self.data),
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_AUTHOR_NAME": "Factory test", "GIT_COMMITTER_NAME": "Factory test",
                    "GIT_AUTHOR_EMAIL": "test@example.invalid", "GIT_COMMITTER_EMAIL": "test@example.invalid"}
        self.env.pop("SOFTWARE_FACTORY_PROJECT", None)
        self.launcher = profile / ".codex/skills/factory/factory.py"
        self.run_cli([sys.executable, SOURCE / "install.py"])
        self.addCleanup(self.run_cli, [sys.executable, self.launcher, "dashboard", "stop"])

    def run_cli(self, args, cwd=None, stdin=None, code=0):
        result = subprocess.run(list(map(str, args)), cwd=cwd or self.temp, env=self.env,
                                input=stdin, capture_output=True, encoding="utf-8", errors="replace", timeout=90)
        self.assertEqual(result.returncode, code, f"{args}\n{result.stdout}\n{result.stderr}")
        return result

    def app(self, name, slots=1):
        path = self.temp / name
        self.run_cli(["git", "init", "-b", "main", path])
        config = path / ".factory/project.json"
        config.parent.mkdir()
        config.write_text(json.dumps({"name": name, "concurrency": slots, "checks": {
            "windows": {"shell": "pwsh", "script": "ci.ps1"},
            "linux": {"shell": "bash", "script": "ci.sh"}}}), encoding="utf-8")
        (path / "ci.ps1").write_text("if (Test-Path fail.txt) { exit 7 }; 'checks passed'\n", encoding="utf-8")
        (path / "ci.sh").write_text("test ! -e fail.txt\n", encoding="utf-8")
        self.run_cli(["git", "add", "."], path)
        self.run_cli(["git", "commit", "-qm", "baseline"], path)
        return path

    def factory(self, project, *args, **kwargs):
        return self.run_cli([sys.executable, self.launcher, *args], project, **kwargs)

    def registration(self, app):
        return json.loads(self.factory(app, "register").stdout)

    def local_job(self, app, *owner, title="Same task", code=0):
        return self.factory(app, "job", *owner, "create-local", title, stdin="Build feature", code=code)

    def test_two_projects_share_board_with_separate_limits_and_artifacts(self):
        api = self.app("Orders API", 2)
        ui = self.app("Storefront")
        with concurrent.futures.ThreadPoolExecutor() as executor:
            runs = list(executor.map(lambda app: self.factory(app, "job", "claim", "--dashboard"), [api, ui]))
        urls = [r.stderr.split("Live dashboard: ")[1].strip() for r in runs]
        self.assertEqual(urls[0], urls[1])
        owners = [["--run", r.stdout.strip()] for r in runs]
        jobs = [self.local_job(app, *owner).stdout.strip() for app, owner in zip((api, ui), owners)]
        self.assertEqual(jobs[0], jobs[1])
        data = [self.registration(app) for app in (api, ui)]
        dirs = [Path(r["jobs"]) / j for r, j in zip(data, jobs)]
        records = [json.loads((d / "job.json").read_bytes()) for d in dirs]
        self.assertNotEqual(records[0]["preview_port"], records[1]["preview_port"])
        self.assertIn("owns this checkout", self.factory(ui, "job", "claim", code=1).stderr)
        self.local_job(api, *owners[0], title="Second order")
        self.assertIn("concurrency 2", self.local_job(api, *owners[0], code=1).stderr)
        self.assertIn("concurrency 1", self.local_job(ui, *owners[1], code=1).stderr)
        for app, owner in zip((api, ui), owners):
            self.factory(app, "job", *owner, "release")
        base = urls[0].removesuffix("dashboard.html")
        with urllib.request.urlopen(base + "projects.json", timeout=5) as response:
            board = json.load(response)
        self.assertEqual(len(board["jobs"]), 3)
        self.assertEqual({p["concurrency"] for p in board["projects"]}, {1, 2})
        for project, directory in zip(data, dirs):
            (directory / "issue.md").write_text(project["name"], encoding="utf-8")
            url = f"{base}projects/{project['project_id']}/jobs/{directory.name}/issue.md"
            self.assertEqual(urllib.request.urlopen(url).read().decode(), project["name"])
        self.factory(api, "dashboard", "stop")
        self.assertEqual(self.factory(ui, "dashboard", "start").stdout.strip(), urls[0])

    def test_worktree_gate_and_recovery(self):
        app = self.app("Mixed project")
        job_id = self.local_job(app).stdout.strip()
        d = Path(self.registration(app)["jobs"]) / job_id
        (d / "intake.md").write_text("DECISION: ACCEPT\nRISK: low\nSURFACES: none\n\nBuild it\n", encoding="utf-8")
        self.factory(app, "route", job_id)
        self.factory(app, "job", "advance", job_id, "spec")
        work = Path(json.loads((d / "job.json").read_bytes())["worktree"])
        self.assertEqual(self.registration(work)["project_id"], self.registration(app)["project_id"])
        (d / "spec.md").write_text("Change the application")
        self.factory(app, "job", "advance", job_id, "build")
        (work / "fail.txt").write_text("regression")
        self.run_cli(["git", "add", "."], work)
        self.run_cli(["git", "commit", "-qm", "regression"], work)
        (d / "build.md").write_text("STATUS: READY\n")
        self.factory(app, "job", "advance", job_id, "gate")
        self.factory(app, "gate", job_id, code=1)
        self.assertIn("GATE: FAIL", (d / "round-1/checks.md").read_text())
        self.factory(app, "job", "advance", job_id, "build")
        self.run_cli(["git", "rm", "fail.txt"], work)
        (work / "feature.txt").write_text("done")
        self.run_cli(["git", "add", "."], work)
        self.run_cli(["git", "commit", "-qm", "feature"], work)
        self.factory(app, "job", "advance", job_id, "gate")
        self.factory(app, "gate", job_id)
        self.factory(app, "job", "advance", job_id, "review")
        sha = self.run_cli(["git", "rev-parse", "HEAD"], work).stdout.strip()
        (d / "round-2/review-code.md").write_text(f"VERDICT: PASS\nCOMMIT: {sha}\n")
        self.factory(app, "job", "advance", job_id, "approve")
        (d / "decision.md").write_text("APPROVE\n")
        self.factory(app, "job", "ready", job_id)
        self.assertEqual(json.loads((d / "job.json").read_bytes())["handoff"], "ready")
        self.local_job(app, title="Next task")
        self.run_cli(["git", "merge", "--ff-only", f"factory/{job_id}"], app)
        self.factory(app, "job", "complete-local", job_id)
        self.assertFalse(work.exists())

    def test_github_queue_shares_slots_with_disconnected_jobs(self):
        api = self.app("Service", 2)
        ui = self.app("Client", 1)
        tools = self.temp / "gh-tools"
        tools.mkdir()
        stub = tools / "fake_gh.py"
        stub.write_text("""import json, sys
args = sys.argv[1:]
if args[:2] == ["issue", "view"]:
    print(json.dumps(dict(number=42, title="Same issue", body="Test", author=dict(login="tester"),
                          labels=[dict(name="factory")], state="OPEN", url="", comments=[])))
elif args[:2] == ["issue", "list"]:
    print(json.dumps([dict(number=42, title="Same issue"), dict(number=43, title="Next")]))
elif args[0] == "api":
    print("tester")
else:
    raise SystemExit("unexpected GitHub call")
""", encoding="utf-8")
        if os.name == "nt":
            (tools / "gh.cmd").write_text(f'@"{sys.executable}" "%~dp0fake_gh.py" %*\r\n')
        else:
            shim = tools / "gh"
            shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{stub}" "$@"\n')
            shim.chmod(0o755)
        self.env["PATH"] = str(tools) + os.pathsep + self.env["PATH"]
        for app in (api, ui):
            self.run_cli(["git", "remote", "add", "origin", "."], app)
            self.factory(app, "job", "create", "42")
        j = self.local_job(api).stdout.strip()
        self.assertIn("hold\t43", self.factory(api, "job", "queue").stdout)
        self.assertIn("concurrency 1", self.local_job(ui, code=1).stderr)
        reg = self.registration(api)
        task = Path(reg["jobs"]) / j
        (task / "intake.md").write_text("DECISION: NEEDS-INFO\n\nClarify the requirement.")
        self.factory(api, "job", "advance", j, "needs-info")
        self.assertIn("new\t43", self.factory(api, "job", "queue").stdout)
        self.local_job(api, title="Use released slot")
        self.assertIn("concurrency 2", self.factory(api, "job", "clarify-local", j, stdin="Details", code=1).stderr)
        cfg = api / ".factory/project.json"
        settings = json.loads(cfg.read_bytes())
        settings["concurrency"] = 1
        cfg.write_text(json.dumps(settings))
        self.assertIn("concurrency 1", self.local_job(api, code=1).stderr)
        self.assertIn("hold\t43", self.factory(ui, "job", "queue").stdout)

    def legacy(self, root):
        command = ["git", "-C", str(SOURCE), "archive", "--format=zip", LEGACY,
                   ".agents", ".codex", "factory", "AGENTS.md", "INSTALL.md", ".gitignore"]
        archive = subprocess.check_output(command)
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            package.extractall(root)

    def test_cleanup_scoped_idempotent_and_restorable(self):
        app = self.app("Legacy app")
        other = self.app("Other project")
        self.legacy(app)
        sub = app / "src"
        sub.mkdir()
        custom = app / ".codex/agents/unrelated.toml"
        custom.write_text("name = 'keep'")
        (app / "PROJECT.local.md").write_text("project notes")
        hist = app / "factory/jobs/014-historical"
        hist.mkdir(parents=True)
        record = {"id": hist.name, "issue": 42, "title": "Archived task", "stage": "needs-human",
                  "round": 0, "pr": None, "ended": None, "started": "2026-01-01T00:00:00Z"}
        (hist / "job.json").write_text(json.dumps(record))
        self.assertIn("Pending", self.factory(sub, "cleanup", code=2).stderr)
        self.assertIn("legacy factory", self.factory(app, "job", "claim", code=1).stderr)
        self.local_job(other)
        record["stage"] = "merged"
        (hist / "job.json").write_text(json.dumps(record))
        (hist / "issue.md").write_text("archive body")
        self.assertIn("Preview only", self.factory(sub, "cleanup").stdout)
        self.assertTrue((app / "factory/bin/job").exists())
        result = self.factory(sub, "cleanup", "--apply")
        self.assertIn("Migrated", result.stdout)
        backup = Path(result.stdout.split("Backup: ")[1].splitlines()[0])
        self.assertEqual((backup / "PROJECT.local.md").read_text(), "project notes")
        self.assertFalse((app / ".agents/skills/factory/SKILL.md").exists())
        self.assertEqual(custom.read_text(), "name = 'keep'")
        state = Path(self.registration(app)["jobs"])
        self.assertEqual((state / hist.name / "issue.md").read_text(), "archive body")
        self.assertIn("Already clean", self.factory(sub, "cleanup", "--apply").stdout)
        self.assertEqual(len(list(backup.parent.iterdir())), 1)
        self.assertIn("Same", self.factory(other, "status").stdout.replace("same", "Same"))
        manifest = json.loads((backup / "migration-manifest.json").read_bytes())
        for rel in manifest["files"]:
            dest = app / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup / rel, dest)
        restored = self.run_cli([sys.executable, app / "factory/bin/job", "project"], cwd=app)
        self.assertEqual(Path(restored.stdout.strip()), app)
        self.assertEqual((hist / "issue.md").read_text(), "archive body")

    def test_cleanup_changed_preview_interrupted_preflight_and_retry(self):
        app = self.app("Interrupted migration")
        self.legacy(app)
        preview = self.factory(app, "cleanup").stdout.split("Preview ID: ")[1].splitlines()[0]
        (app / "PROJECT.local.md").write_text("new notes")
        changed = self.factory(app, "cleanup", "--apply", "--expect", preview, code=1)
        self.assertIn("preview has changed", changed.stderr)
        (app / "fail.txt").touch()
        failed = self.factory(app, "cleanup", "--apply", code=1)
        self.assertIn("preflight failed", failed.stderr)
        self.assertTrue((app / "factory/bin/job").exists())
        (app / "fail.txt").unlink()
        self.assertIn("Migrated", self.factory(app, "cleanup", "--apply").stdout)
        self.assertIn("Already clean", self.factory(app, "cleanup").stdout)
        self.assertEqual(len(list(self.data.glob("backups/*/*/migration-manifest.json"))), 1)

    def test_external_cleanup_and_shared_user_files(self):
        app = self.app("External app")
        ext = self.temp / "Old separate factory"
        self.legacy(ext)
        (ext / ".factory-project.local.json").write_text(json.dumps({"checkout": str(app)}))
        (ext / "factory/checks.ps1").write_text("Write-Output 'custom imported check'")
        self.factory(app, "discover", "--remember", str(ext))
        unrelated = ext / "personal.txt"
        unrelated.write_text("keep")
        self.assertIn("Migrated", self.factory(app, "cleanup", "--apply").stdout)
        self.assertTrue(unrelated.is_file())
        self.assertIn("Already clean", self.factory(app, "cleanup").stdout)
        self.assertEqual(len(list((self.temp / "profile/.codex/agents").glob("factory-*.toml"))), 9)
        self.run_cli([sys.executable, SOURCE / "install.py"])
        self.assertTrue(Path(self.registration(app)["notes"]).parent.is_dir())


if __name__ == "__main__":
    unittest.main(verbosity=2)
