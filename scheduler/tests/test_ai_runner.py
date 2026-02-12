import os
import subprocess
import sys
import unittest
from unittest.mock import patch

SCHEDULER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCHEDULER_DIR not in sys.path:
    sys.path.insert(0, SCHEDULER_DIR)

import ai_runner  # noqa: E402


class TestAIRunner(unittest.TestCase):
    def test_run_ai_task_claude_argv(self):
        config = {
            "ai": {
                "provider": "claude",
                "retry": {"max_attempts": 1, "backoff_seconds": 0},
                "claude": {
                    "command": "claude",
                    "mode": "argv",
                    "prompt_arg": "-p",
                    "extra_args": ["--allowedTools", "Read"],
                },
            }
        }

        with patch("ai_runner.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["claude"], returncode=0, stdout="ok", stderr=""
            )
            success, stdout, _ = ai_runner.run_ai_task("news", "hello", config, 1)

        self.assertTrue(success)
        self.assertEqual(stdout, "ok")
        call_args = mock_run.call_args
        call_kwargs = call_args.kwargs
        self.assertEqual(call_args.args[0], ["claude", "-p", "hello", "--allowedTools", "Read"])
        self.assertEqual(call_kwargs["shell"], False)
        self.assertIsNone(call_kwargs["input"])

    def test_run_ai_task_custom_stdin(self):
        config = {
            "ai": {
                "provider": "custom",
                "retry": {"max_attempts": 1, "backoff_seconds": 0},
                "custom": {
                    "command_template": "myai --run",
                    "mode": "stdin",
                    "shell": False,
                },
            }
        }

        with patch("ai_runner.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["myai"], returncode=0, stdout="done", stderr=""
            )
            success, _, _ = ai_runner.run_ai_task("daily", "test prompt", config, 1)

        self.assertTrue(success)
        call_args = mock_run.call_args
        call_kwargs = call_args.kwargs
        self.assertEqual(call_args.args[0], ["myai", "--run"])
        self.assertEqual(call_kwargs["input"], "test prompt")
        self.assertEqual(call_kwargs["shell"], False)

    def test_run_ai_task_custom_argv_shell_false_prompt_token(self):
        config = {
            "ai": {
                "provider": "custom",
                "retry": {"max_attempts": 1, "backoff_seconds": 0},
                "custom": {
                    "command_template": "myai --prompt {prompt}",
                    "mode": "argv",
                    "shell": False,
                },
            }
        }

        with patch("ai_runner.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["myai"], returncode=0, stdout="done", stderr=""
            )
            success, _, _ = ai_runner.run_ai_task("daily", "a prompt with spaces", config, 1)

        self.assertTrue(success)
        call_args = mock_run.call_args
        self.assertEqual(
            call_args.args[0],
            ["myai", "--prompt", "a prompt with spaces"],
        )

    def test_run_ai_task_retry_once_then_success(self):
        config = {
            "ai": {
                "provider": "claude",
                "retry": {"max_attempts": 2, "backoff_seconds": 0},
            }
        }

        first = subprocess.CompletedProcess(args=["claude"], returncode=1, stdout="", stderr="err")
        second = subprocess.CompletedProcess(args=["claude"], returncode=0, stdout="ok", stderr="")

        with patch("ai_runner.subprocess.run", side_effect=[first, second]) as mock_run:
            success, stdout, _ = ai_runner.run_ai_task("news", "hello", config, 1)

        self.assertTrue(success)
        self.assertEqual(stdout, "ok")
        self.assertEqual(mock_run.call_count, 2)

    def test_run_ai_task_timeout(self):
        config = {
            "ai": {
                "provider": "claude",
                "retry": {"max_attempts": 1, "backoff_seconds": 0},
            }
        }

        with patch(
            "ai_runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["claude"], timeout=1),
        ):
            success, _, stderr = ai_runner.run_ai_task("news", "hello", config, 1)

        self.assertFalse(success)
        self.assertIn("Timeout", stderr)

    def test_news_task_requires_output_file(self):
        config = {"ai": {"provider": "claude"}}
        with patch("ai_runner.run_ai_task", return_value=(True, "ok", "")):
            with patch("ai_runner._find_recent_output", return_value=None):
                success, _, stderr = ai_runner.run_news_stock_picker(config)

        self.assertFalse(success)
        self.assertIn("未找到新產生的新聞報告檔案", stderr)

    def test_daily_task_requires_output_file(self):
        config = {"ai": {"provider": "claude"}}
        prefs = {"risk_level": "moderate"}
        with patch("ai_runner.run_ai_task", return_value=(True, "ok", "")):
            with patch("ai_runner._find_recent_output", return_value=None):
                success, _, stderr = ai_runner.run_tw_stock_analyzer(config, prefs)

        self.assertFalse(success)
        self.assertIn("未找到新產生的交易計畫檔案", stderr)


if __name__ == "__main__":
    unittest.main()
