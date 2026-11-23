import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import cleanup


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def factory(self, project):
        base = project / ".factory"
        self.write(base / "installation.json", json.dumps(cleanup.MARKER))
        self.write(base / "factory/config.json", "{}")
        return base

    def run_cleanup(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = cleanup.main([str(arg) for arg in args])
        return status, output.getvalue()

    def test_preview_and_apply_across_nested_projects_preserve_unrelated_content(self):
        first = self.factory(self.root / "a")
        second = self.factory(self.root / "group/b")
        user_file = self.write(self.root / "a/AGENTS.md", "shared instructions")
        unrelated = self.write(self.root / "c/.factory/notes.md", "not our directory")
        self.write(self.root / "c/.factory/installation.json", "unrelated")
        self.write(self.root / "c/.factory/project.json", "other program")
        self.assertEqual(self.run_cleanup(self.root)[0], 0)
        self.assertTrue(first.exists() and second.exists())
        self.assertEqual(self.run_cleanup(self.root, "--apply")[0], 0)
        self.assertFalse(first.exists() or second.exists())
        self.assertTrue(user_file.exists() and unrelated.exists())
        self.assertIn("No recognized", self.run_cleanup(self.root)[1])

    def test_ownership_marker_must_still_match_before_any_deletion(self):
        app = self.root / "app"
        base = self.factory(app)
        record = self.write(base / "factory/jobs/001-done/job.json", '{"id":"001-done","stage":"merged"}')
        plan = cleanup.scan(self.root, False)
        (base / "installation.json").unlink()
        with self.assertRaisesRegex(ValueError, "ownership marker changed"):
            cleanup.apply(plan)
        self.assertTrue(record.exists())

    def test_project_skill_cleanup_stays_in_scope_and_preserves_neighbors(self):
        app = self.root / "app"
        base = self.factory(app)
        skill = app / cleanup.SKILL_DIR
        generated = [self.write(skill / name, text) for name, text in cleanup.ENTRY_FILES.items()]
        neighbor = self.write(skill.parent / "another-skill/SKILL.md", "application skill")
        local = self.write(skill / "notes.txt", "operator notes")
        status, output = self.run_cleanup(base, "--apply")
        self.assertNotEqual(status, 0)
        self.assertIn("include the application root", output)
        self.assertTrue(base.exists() and all(p.exists() for p in generated))
        status, output = self.run_cleanup(app)
        self.assertEqual(status, 0, output)
        for path in generated:
            self.assertIn(f"Remove file: {path}", output)
            self.assertTrue(path.exists())
        status, output = self.run_cleanup(app, "--apply")
        self.assertEqual(status, 0, output)
        self.assertFalse(base.exists() or any(p.exists() for p in generated))
        self.assertTrue(local.exists() and neighbor.exists())

    def test_remove_only_matching_generated_project_skill_files(self):
        for name, content in cleanup.ENTRY_FILES.items():
            with self.subTest(name=name):
                app = self.root / name.strip(".")
                self.factory(app)
                skill = app / cleanup.SKILL_DIR
                other_name = next(key for key in cleanup.ENTRY_FILES if key != name)
                owned = self.write(skill / name, content)
                edited = self.write(skill / other_name, "local edits\n")
                plan = cleanup.scan(app, False)
                owned.write_text("changed since preview")
                with self.assertRaisesRegex(ValueError, "file changed"):
                    cleanup.apply(plan)
                self.assertTrue((app / ".factory/installation.json").is_file())
                owned.write_text(content)
                status, output = self.run_cleanup(app, "--apply")
                self.assertEqual(status, 0, output)
                self.assertFalse(owned.exists())
                self.assertEqual(edited.read_text(), "local edits\n")

    def test_project_skill_does_not_follow_or_unlink_user_junction(self):
        app = self.root / "app"
        base = self.factory(app)
        other = self.factory(self.root / "other")
        for name in ("factory/bin/route", "factory/bin/gate"):
            self.write(other / name, (cleanup.SOURCE / name).read_text())
        target = other / cleanup.SKILL_DIR
        for name, content in cleanup.ENTRY_FILES.items():
            self.write(target / name, content)
        link = app / cleanup.SKILL_DIR
        self.link_directory(link, target)
        status, output = self.run_cleanup(app, "--apply")
        self.assertEqual(status, 0, output)
        self.assertTrue(cleanup.linked(link))
        self.assertTrue((target / "SKILL.md").is_file())
        self.assertFalse(base.exists())

    def test_legacy_cleanup_preserves_mixed_files_and_custom_agent(self):
        app = self.root / "app"
        known = cleanup.fingerprints()
        for name in ("factory/bin/route", "factory/bin/gate"):
            path = app / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((cleanup.SOURCE / name).read_bytes())
            self.assertIn(cleanup.digest(path), known[name])
        config = self.write(app / "factory/config.json", '{"base_branch":"main"}')
        self.write(app / "factory/jobs/001-done/job.json", '{"id":"001-done","stage":"merged"}')
        unrelated = self.write(app / "factory/app.py", "production")
        agents = self.write(app / ".codex/agents/builder.toml", "unrelated builder")
        shared = self.write(app / "AGENTS.md", "# Factory and application instructions")
        status, out = self.run_cleanup(self.root, "--apply")
        self.assertEqual(status, 0, out)
        self.assertFalse(config.exists() or (app / "factory/jobs").exists())
        self.assertTrue(unrelated.exists() and agents.exists() and shared.exists())
        self.assertIn("Review edited or shared", out)

    def test_changed_portable_settings_survive_apply(self):
        path = self.write(self.root / ".factory/project.json", '{"concurrency":2}')
        plan = cleanup.scan(self.root, False, orphan_settings=True)
        path.write_text("updated elsewhere")
        with self.assertRaisesRegex(ValueError, "file changed"):
            cleanup.apply(plan)
        self.assertEqual(path.read_text(), "updated elsewhere")

    def test_whole_clone_requires_an_exact_verified_choice_and_no_source_worktrees(self):
        app = self.root / "app"
        old = self.root / "old factory"
        for name in ("factory/bin/route", "factory/bin/gate"):
            self.write(old / name, (cleanup.SOURCE / name).read_text(encoding="utf-8"))
        self.write(old / cleanup.BINDING, json.dumps({"checkout": str(app)}))
        custom = self.write(old / "custom.md", "local edits")
        app.mkdir()
        for repo in (app, old):
            cleanup.require_git("-C", repo, "init", "-q")
            cleanup.require_git("-C", repo, "-c", "user.name=Test", "-c", "user.email=test@example.com",
                                "commit", "--allow-empty", "-qm", "init")
        cleanup.require_git("-C", old, "remote", "add", "origin", "https://github.com/mapelli0/software-factory-codex.git")
        wrapper = self.root / "system" / cleanup.SKILL
        (old / cleanup.SKILL).mkdir(parents=True)
        self.link_directory(wrapper, old / cleanup.SKILL)
        status, out = self.run_cleanup(self.root, "--apply")
        self.assertEqual(status, 0, out)
        self.assertTrue((old / cleanup.BINDING).exists() and custom.exists() and cleanup.linked(wrapper))
        option = "--remove-legacy-clone"
        for scope, candidate in ((app, old), (self.root, app)):
            status, out = self.run_cleanup(scope, option, candidate, "--apply")
            self.assertNotEqual(status, 0, out)
            self.assertTrue(custom.exists() and (app / ".git").exists())
        extra = self.root / "extra"
        cleanup.require_git("-C", old, "worktree", "add", "-q", "--detach", extra)
        status, out = self.run_cleanup(self.root, option, old, "--apply")
        self.assertNotEqual(status, 0, out)
        self.assertIn("extra worktrees", out)
        cleanup.require_git("-C", old, "worktree", "remove", extra)
        cleanup.require_git("-C", old, "remote", "set-url", "origin", "https://github.com/example/unrelated")
        status, out = self.run_cleanup(self.root, option, old, "--apply")
        self.assertNotEqual(status, 0, out)
        self.assertTrue(custom.exists() and cleanup.linked(wrapper))
        cleanup.require_git("-C", old, "remote", "set-url", "origin", "git@github.com:mapelli0/software-factory-codex.git")
        record = self.write(old / "factory/jobs/001-build/job.json", '{"id":"001-build","stage":"build"}')
        status, out = self.run_cleanup(self.root, option, old, "--apply")
        self.assertNotEqual(status, 0, out)
        self.assertTrue(record.exists())
        record.write_text('{"id":"001-build","stage":"merged"}')
        status, out = self.run_cleanup(self.root, option, old)
        self.assertEqual(status, 0, out)
        self.assertIn("including .git, job history and all local edits", out)
        self.assertTrue(custom.exists())
        status, out = self.run_cleanup(self.root, option, old, "--apply")
        self.assertEqual(status, 0, out)
        self.assertFalse(old.exists() or cleanup.linked(wrapper))
        self.assertTrue((app / ".git").exists())

    def test_git_marker_and_portable_settings(self):
        app = self.root / "a"
        config = self.write(app / ".git/config", '[user]\n name = me\n[softwarefactory]\n projectid = ' + "a" * 32)
        settings = self.write(app / ".factory/project.json", '{"name":"A"}')
        lone = self.write(self.root / "b/.git/config", '[softwarefactory]\n projectid = ' + "b" * 32)
        unknown = self.write(self.root / "c/.factory/project.json", '{"name":"other product"}')
        orphan = self.write(self.root / "d/.factory/project.json", '{"max_rounds":3}')
        status, out = self.run_cleanup(self.root, "--apply")
        self.assertEqual(status, 0, out)
        self.assertFalse(settings.exists())
        self.assertIn("name = me", config.read_text())
        self.assertIsNone(cleanup.git_id(config))
        self.assertIsNone(cleanup.git_id(lone))
        self.assertTrue(unknown.exists())
        self.assertTrue(orphan.exists())
        status, out = self.run_cleanup(orphan.parent.parent, "--orphan-settings", "--apply")
        self.assertEqual(status, 0, out)
        self.assertFalse(orphan.exists())

    def link_directory(self, link, target):
        link.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            env = dict(os.environ, FACTORY_TEST_LINK=str(link), FACTORY_TEST_TARGET=str(target))
            subprocess.run(["pwsh", "-NoProfile", "-Command",
                            "New-Item -ItemType Junction -Path $env:FACTORY_TEST_LINK "
                            "-Target $env:FACTORY_TEST_TARGET -ErrorAction Stop | Out-Null"], env=env, check=True)
        else:
            link.symlink_to(target, target_is_directory=True)

    def test_unlink_only_verified_factory_junctions_without_following_targets(self):
        scan = self.root / "scope"
        outside = self.root / "elsewhere"
        base = self.factory(outside / "linked-app")
        self.link_directory(scan / "linked-app", base.parent)
        for name in ("factory/bin/route", "factory/bin/gate"):
            path = outside / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((cleanup.SOURCE / name).read_bytes())
        for role in (cleanup.SKILL, cleanup.AGENTS):
            (outside / role).mkdir(parents=True)
            self.link_directory(scan / role, outside / role)
        status, out = self.run_cleanup(scan, "--apply")
        self.assertEqual(status, 0, out)
        for role in (cleanup.SKILL, cleanup.AGENTS):
            self.assertFalse(cleanup.linked(scan / role))
            self.assertTrue((outside / role).exists())
        self.assertTrue((base / "installation.json").exists())
        self.assertTrue(cleanup.linked(scan / "linked-app"))

    def test_dirty_worktree_and_active_owner_block_even_explicit_discard(self):
        app = self.root / "app"
        base = self.factory(app)
        def git(*args):
            return cleanup.require_git("-C", app, *args)
        git("init", "-q")
        self.write(app / ".gitignore", ".env\n")
        git("add", ".gitignore")
        git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "initial")
        job = "001-task"
        record = self.write(base / "factory/jobs" / job / "job.json",
                            json.dumps({"id": job, "stage": "build"}))
        tree = base / ".worktrees" / job
        git("worktree", "add", "-qb", "factory/" + job, tree)
        owner = self.write(base / "factory/jobs/.owner", "active")
        self.assertNotEqual(self.run_cleanup(app, "--apply", "--discard-jobs")[0], 0)
        owner.unlink()
        dirty = self.write(tree / "changes", "pending work")
        self.assertNotEqual(self.run_cleanup(app, "--apply", "--discard-jobs")[0], 0)
        self.assertTrue(dirty.exists() and record.exists())
        dirty.unlink()
        self.assertNotEqual(self.run_cleanup(app, "--apply")[0], 0)
        record.write_text(json.dumps({"id": job, "stage": "merged"}))
        ignored = self.write(tree / ".env", "local")
        self.assertNotEqual(self.run_cleanup(app, "--apply")[0], 0)
        self.assertTrue(ignored.exists())
        status, out = self.run_cleanup(base, "--apply", "--discard-jobs")
        self.assertNotEqual(status, 0)
        self.assertIn("include the checkout", out)
        self.assertTrue(ignored.exists())
        status, out = self.run_cleanup(app, "--apply", "--discard-jobs")
        self.assertEqual(status, 0, out)
        self.assertFalse(base.exists())
        self.assertIn(b"refs/heads/factory/001-task", git("show-ref"))
        self.assertNotIn(b"001-task", git("worktree", "list", "--porcelain"))


if __name__ == "__main__":
    unittest.main()
