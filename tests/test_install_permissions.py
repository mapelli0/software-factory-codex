"""Exercise permission setup through the installer using a disposable Codex home."""

import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]


class InstallPermissionsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="factory permissions ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.codex = self.root / "codex"
        self.codex.mkdir()
        self.data = self.root / "factory data"
        self.config = self.codex / "config.toml"
        self.env = {**os.environ, "CODEX_HOME": str(self.codex), "SOFTWARE_FACTORY_HOME": str(self.data)}

    def install(self, *args):
        result = subprocess.run([sys.executable, str(SOURCE / "install.py"), *args], env=self.env,
                                cwd=self.root, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout + result.stderr

    def assert_profile(self):
        settings = tomllib.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(settings["default_permissions"], "factory")
        self.assertEqual(settings["permissions"], {
            "factory": {"extends": ":workspace", "workspace_roots": {self.data.as_posix(): True}}})

    def test_fresh_user_and_opt_out(self):
        self.install("--skip-permissions")
        self.assertFalse(self.config.exists())
        self.assertTrue((self.codex / "skills/factory/factory.py").exists())
        self.assertIn("Set the user default", self.install())
        self.assert_profile()
        original = self.config.read_bytes()
        self.assertIn("already includes", self.install())
        self.assertEqual(self.config.read_bytes(), original)

    def test_existing_settings_and_comments_survive(self):
        original = b'# user settings\r\napproval_policy = "on-request"\r\n[features]\r\n# trailing comment'
        self.config.write_bytes(original)
        self.assertIn("Set the user default", self.install())
        self.assert_profile()
        updated = self.config.read_bytes()
        self.assertIn(original, updated)
        self.assertNotIn(b"\n", updated.replace(b"\r\n", b""))

    def test_preserves_explicit_permissions_and_malformed_config(self):
        for content, message in [
            ('default_permissions = ":read-only"', "Kept your existing"),
            ('sandbox_mode = "read-only"', "Kept your existing"),
            ('[sandbox_workspace_write]\nnetwork_access = false', "Kept your existing"),
            ('[permissions.factory]\nextends = ":read-only"', "Kept your existing"),
            ('[broken', "needs attention"),
        ]:
            with self.subTest(content=content):
                self.config.write_bytes(content.encode())
                self.assertIn(message, self.install())
                self.assertEqual(self.config.read_bytes(), content.encode())

    @unittest.skipUnless(os.name == "nt", "Windows packaged app paths")
    def test_windows_sessions_share_persistent_data(self):
        del self.env["SOFTWARE_FACTORY_HOME"]
        local = self.root / "Redirected Local"
        self.data = local / "software-factory-codex"
        for session in ("first", "second"):
            container = local / "Packages" / "OpenAI.Codex_test" / "AC" / f"#!sandbox.{session}"
            self.env["LOCALAPPDATA"] = str(container)
            self.install()
            self.assertFalse(container.exists())
            self.assert_profile()
        self.assertTrue((self.data / "installation.json").is_file())
