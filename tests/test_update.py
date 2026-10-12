"""Exercise updates against a local Git remote without internet access."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import app_update
from app_update import UpdateError, check_for_update, install_update


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.remote = root / "remote.git"
        self.publisher = root / "publisher"
        self.installed = root / "installed"
        self.git(root, "init", "--bare", str(self.remote))
        self.git(root, "clone", str(self.remote), str(self.publisher))
        self.git(self.publisher, "checkout", "-b", "main")
        (self.publisher / "main.py").write_text("print('old')\n", encoding="utf-8")
        (self.publisher / "requirements.txt").write_text("\n", encoding="utf-8")
        self.commit("initial")
        self.git(self.publisher, "push", "-u", "origin", "main")
        self.git(root, "clone", "--branch", "main", str(self.remote), str(self.installed))

    def git(self, cwd, *args):
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def commit(self, message):
        self.git(self.publisher, "add", "--all")
        self.git(self.publisher, "-c", "user.name=Test", "-c", "user.email=test@example.com",
                 "commit", "-m", message)

    def test_one_click_update_keeps_local_data_and_settings(self):
        (self.installed / "logs").mkdir()
        data = self.installed / "logs" / "measurement.csv"
        data.write_text("time,voltage\n1,2\n", encoding="utf-8")
        settings = self.installed / "recording_settings.json"
        settings.write_text('{"max_data_lines": 25}\n', encoding="utf-8")
        (self.publisher / "main.py").write_text("print('new')\n", encoding="utf-8")
        self.commit("new version")
        self.git(self.publisher, "push")

        info = check_for_update(self.installed)
        self.assertTrue(info.needs_update)
        self.assertFalse(info.requirements_changed)
        install_update(self.installed, info)
        self.assertEqual((self.installed / "main.py").read_text(encoding="utf-8"),
                         "print('new')\n")
        self.assertEqual(data.read_text(encoding="utf-8"), "time,voltage\n1,2\n")
        self.assertEqual(settings.read_text(encoding="utf-8"), '{"max_data_lines": 25}\n')
        self.assertFalse(check_for_update(self.installed).needs_update)

    def test_local_code_change_blocks_update_without_overwriting(self):
        path = self.installed / "main.py"
        path.write_text("site edit\n", encoding="utf-8")
        with self.assertRaisesRegex(UpdateError, "Local code changes"):
            check_for_update(self.installed)
        self.assertEqual(path.read_text(encoding="utf-8"), "site edit\n")

    def test_dependency_failure_leaves_old_code_in_place(self):
        (self.publisher / "requirements.txt").write_text("new-package==1\n", encoding="utf-8")
        (self.publisher / "main.py").write_text("print('new')\n", encoding="utf-8")
        self.commit("new dependency")
        self.git(self.publisher, "push")
        info = check_for_update(self.installed)
        self.assertTrue(info.requirements_changed)
        actual_run = app_update._run

        def fail_pip(*args, repo, timeout=120):
            if args[:3] == (sys.executable, "-m", "pip"):
                raise UpdateError("package installation failed")
            return actual_run(*args, repo=repo, timeout=timeout)

        with patch("app_update._run", side_effect=fail_pip):
            with self.assertRaisesRegex(UpdateError, "package installation failed"):
                install_update(self.installed, info)
        self.assertEqual(self.git(self.installed, "rev-parse", "HEAD"), info.current)
        self.assertEqual((self.installed / "main.py").read_text(encoding="utf-8"),
                         "print('old')\n")


if __name__ == "__main__":
    unittest.main()
