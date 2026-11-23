import codecs
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from uninstall_global import uninstall


class GlobalRollbackTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name).resolve()
        self.codex = directory / "Codex Home"
        self.skill = self.codex / "skills/factory"
        self.launcher = self.skill / "factory.py"
        self.role = self.codex / "agents/factory-builder.toml"
        self.data = directory / "Factory Data"
        self.receipt = self.data / "installation.json"
        self.data.mkdir()
        self.files = {}
        for path in (self.launcher, self.role):
            path.parent.mkdir(parents=True)
            path.write_bytes(b"installation payload")
            self.files[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.write_receipt()
        self.original = '# user preferences\r\n[projects."sample"]\r\ntrust_level = "trusted"\r\n'
        self.profile = ('[permissions.factory]\r\nextends = ":workspace"\r\n\r\n'
                        f'[permissions.factory.workspace_roots]\r\n"{self.data.as_posix()}" = true\r\n')
        self.config = self.codex / "config.toml"
        self.config.write_bytes(codecs.BOM_UTF8 + ('default_permissions = "factory"\r\n'
                                + self.original + '\r\n' + self.profile).encode())

    def write_receipt(self):
        self.receipt.write_text(json.dumps({"runtime": str(self.skill), "files": self.files}))

    def run_uninstall(self, apply=False):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            uninstall(self.codex, self.data, apply)
        return output.getvalue()

    def test_preview_then_apply_and_retry(self):
        original_config = self.config.read_bytes()
        related = self.data / "handoff.md"
        unrelated = self.role.with_name("other-role.toml")
        for path in (related, unrelated):
            path.write_bytes(b"preserve")
        self.assertIn(str(self.role), self.run_uninstall())
        self.assertEqual(self.config.read_bytes(), original_config)
        self.assertTrue(self.launcher.is_file())
        self.run_uninstall(apply=True)
        self.assertFalse(self.skill.exists())
        self.assertFalse(self.role.exists())
        self.assertFalse(self.receipt.exists())
        self.assertEqual(self.config.read_bytes(), codecs.BOM_UTF8 + self.original.encode())
        for path in (related, unrelated):
            self.assertEqual(path.read_bytes(), b"preserve")
        self.assertIn("No global installation", self.run_uninstall(apply=True))

    def test_preserves_custom_permissions_and_unrelated_content(self):
        custom = self.config.read_bytes() + b'"C:/another_folder" = true\r\n'
        self.config.write_bytes(custom)
        self.assertIn("Kept customized", self.run_uninstall(apply=True))
        self.assertEqual(self.config.read_bytes(), custom)

    def test_unexpected_receipt_file_or_edited_role_aborts_before_removal(self):
        other = self.codex / "private"
        other.write_bytes(b"installation payload")
        self.files[str(other)] = self.files[str(self.role)]
        self.write_receipt()
        with self.assertRaisesRegex(ValueError, "unexpected entry"):
            self.run_uninstall(apply=True)
        del self.files[str(other)]
        self.write_receipt()
        self.role.write_bytes(b"custom model")
        with self.assertRaisesRegex(ValueError, "locally edited"):
            self.run_uninstall(apply=True)
        self.assertTrue(self.launcher.exists())
        self.assertTrue(self.receipt.exists())
        self.assertTrue(other.exists())

    def test_pauses_for_active_runs_and_dashboard(self):
        owner = self.data / "projects/any/jobs/.owner"
        owner.parent.mkdir(parents=True)
        owner.write_text("run")
        with self.assertRaisesRegex(ValueError, "active factory run"):
            self.run_uninstall(apply=True)
        owner.unlink()
        (self.data / "dashboard.json").write_text('{"token":"live"}')
        with self.assertRaisesRegex(ValueError, "stop the global dashboard"):
            self.run_uninstall(apply=True)
        self.assertTrue(self.launcher.exists())

    def test_linked_ancestor_aborts_before_removal(self):
        outside = self.codex.parent / "outside"
        self.role.parent.rename(outside)
        try:
            self.role.parent.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "without links"):
            self.run_uninstall(apply=True)
        self.assertTrue(self.launcher.exists())
        self.assertTrue((outside / self.role.name).exists())
