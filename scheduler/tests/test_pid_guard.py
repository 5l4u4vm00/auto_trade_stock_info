import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scheduler.app.pid_guard import check_pid, remove_pid, write_pid


class PidGuardTest(unittest.TestCase):
    def test_write_and_remove_pid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pid_path = Path(temp_dir) / "scheduler.pid"

            write_pid(pid_path)
            self.assertTrue(pid_path.exists())

            remove_pid(pid_path)
            self.assertFalse(pid_path.exists())

    def test_check_pid_running_should_exit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pid_path = Path(temp_dir) / "scheduler.pid"
            pid_path.write_text("12345", encoding="utf-8")

            with patch("scheduler.app.pid_guard.os.kill", return_value=None):
                with self.assertRaises(SystemExit):
                    check_pid(pid_path)

    def test_check_pid_stale_should_remove_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pid_path = Path(temp_dir) / "scheduler.pid"
            pid_path.write_text("12345", encoding="utf-8")

            with patch(
                "scheduler.app.pid_guard.os.kill",
                side_effect=ProcessLookupError,
            ):
                check_pid(pid_path)

            self.assertFalse(pid_path.exists())


if __name__ == "__main__":
    unittest.main()

