"""OpenSpec source selection and scope verification without requiring the optional CLI."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "factory" / "bin"))
import openspec_flow as flow


class OpenSpecAdapterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.app = self.root / "nested"
        self.app.mkdir()
        self.change = self.root / "openspec/changes/demo"
        self.change.mkdir(parents=True)

    def test_root_from_cli_wins_over_nearer_directory_and_rejects_foreign_paths(self):
        (self.app / "openspec").mkdir()
        self.assertEqual(flow._planning_root(self.app, {"root": {"path": str(self.root)}}), self.root)
        self.assertEqual(flow._planning_root(self.app, {}, fallback=self.root), self.root)
        self.assertEqual(flow._planning_root(self.app, {}), self.app)
        other = self.root / "other"
        (other / "openspec").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "outside"):
            flow._planning_root(self.app, {"root": {"path": str(other)}})
        for raw in (str(self.root / "secret.md"), "../outside.md"):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "outside"):
                flow._documents(self.change, {}, {"contextFiles": {"design": [raw]}})

    def test_digest_normalizes_transfer_format_and_only_the_tracking_file_checkboxes(self):
        tasks = [{"id": "1", "description": "Build", "done": False}]
        original = {"plan.md": "# Plan\n- [ ] Criterion\n", "work.md": "# Work\n- [ ] Build\n"}
        digest, tracking = flow._scope_digest("demo", "custom", original, {}, tasks)
        self.assertEqual(tracking, "work.md")
        transferred = {p: "\ufeff" + b.replace("\n", "\r\n") for p, b in original.items()}
        tasks[0]["done"] = True
        transferred["work.md"] = transferred["work.md"].replace("[ ]", "[X]")
        self.assertEqual(flow._scope_digest("demo", "custom", transferred, {}, tasks), (digest, tracking))
        transferred["plan.md"] = transferred["plan.md"].replace("[ ]", "[x]")
        self.assertNotEqual(flow._scope_digest("demo", "custom", transferred, {}, tasks)[0], digest)

    def test_legacy_nested_checkout_uses_app_cli_and_parent_cwd_for_all_change_queries(self):
        (self.change / "proposal.md").write_text("A draft", encoding="utf-8")
        listing = {"changes": [{"name": "demo", "totalTasks": 0, "completedTasks": 0}]}
        status = {"changeName": "demo", "schemaName": "spec-driven",
                  "artifacts": [{"id": "proposal", "status": "done", "outputPath": "proposal.md"}]}
        apply = {"changeName": "demo", "state": "blocked", "tasks": [], "contextFiles": {},
                 "progress": {"total": 0, "complete": 0, "remaining": 0}}
        for nested_response in ({"changes": []}, flow._CommandError("missing changes directory")):
            with self.subTest(nested_response=nested_response), patch.object(
                flow, "_query", side_effect=[nested_response, listing, status, apply]
            ) as query:
                selected = flow.inspect_change(self.app, "demo")
                self.assertEqual(selected["root"], str(self.root))
                self.assertEqual(selected["documents"], {"proposal.md": "A draft"})
                self.assertEqual(query.call_args_list, [
                    call(self.app, "list"),
                    call(self.app, "list", cwd=self.root),
                    call(self.app, "status", "--change", "demo", cwd=self.root),
                    call(self.app, "instructions", "apply", "--change", "demo", cwd=self.root),
                ])

    def test_root_aware_fallback_cannot_hide_a_broken_application_configuration(self):
        report = {"root": {"path": str(self.root)}, "changes": []}
        with patch.object(flow, "_query", side_effect=[flow._CommandError("invalid app config"), report]):
            with self.assertRaisesRegex(ValueError, "invalid app config"):
                flow.list_changes(self.app)

    def test_indentation_is_matched_against_the_actual_cli_task_list(self):
        body = {"tasks.md": "- [ ] First\n    - [ ] Nested\n"}
        tasks = [{"id": "1", "description": "First", "done": False}]
        groups = {"tasks": {"tasks.md"}}
        digest = flow._scope_digest("demo", "schema", body, groups, tasks)[0]
        modified = {"tasks.md": body["tasks.md"].replace("    - [ ]", "    - [x]")}
        self.assertNotEqual(flow._scope_digest("demo", "schema", modified, groups, tasks)[0], digest)
        tasks.append({"id": "2", "description": "Nested", "done": False})
        digest = flow._scope_digest("demo", "schema", body, groups, tasks)[0]
        tasks[1]["done"] = True
        self.assertEqual(flow._scope_digest("demo", "schema", modified, groups, tasks)[0], digest)

    def test_cli_priority_and_change_id_safety(self):
        name = "openspec.cmd" if os.name == "nt" else "openspec"
        parent_cli = self.root / "node_modules" / ".bin" / name
        project_cli = self.app / "node_modules" / ".bin" / name
        with patch.dict(os.environ, {"PATH": ""}):
            with self.assertRaisesRegex(ValueError, "CLI not found"):
                flow._executable(self.app)
            for cli in (parent_cli, project_cli):
                cli.parent.mkdir(parents=True)
                cli.touch()
                cli.chmod(0o755)
                self.assertEqual(flow._executable(self.app), cli)
        with patch.object(flow, "_query") as query:
            for name in ("-bad", "demo&pause", "demo/path", "demo%path%", "archive"):
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "invalid OpenSpec change ID"):
                    flow.inspect_change(self.app, name)
            query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
