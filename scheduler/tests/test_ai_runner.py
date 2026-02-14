import os
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import mock_open, patch

SCHEDULER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCHEDULER_DIR not in sys.path:
    sys.path.insert(0, SCHEDULER_DIR)

import ai_runner  # noqa: E402


class TestAIRunner(unittest.TestCase):
    def _create_skill_dir(self, root_path, skill_name):
        skill_dir = os.path.join(root_path, skill_name)
        os.makedirs(skill_dir, exist_ok=True)
        skill_file = os.path.join(skill_dir, "SKILL.md")
        with open(skill_file, "w", encoding="utf-8") as file_obj:
            file_obj.write(f"# {skill_name}\n")
        return skill_dir

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

    def test_run_ai_task_codex_stdin(self):
        config = {
            "ai": {
                "provider": "codex",
                "retry": {"max_attempts": 1, "backoff_seconds": 0},
                "codex": {
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

    def test_run_ai_task_codex_argv_shell_false_prompt_token(self):
        config = {
            "ai": {
                "provider": "codex",
                "retry": {"max_attempts": 1, "backoff_seconds": 0},
                "codex": {
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
        config = {
            "ai": {
                "provider": "claude",
                "skill_enforcement": {"enabled": False},
            }
        }
        with patch("ai_runner.run_ai_task", return_value=(True, "ok", "")):
            with patch("ai_runner._find_recent_output", return_value=None):
                success, _, stderr = ai_runner.run_news_stock_picker(config)

        self.assertFalse(success)
        self.assertIn("未找到新產生的新聞報告檔案", stderr)

    def test_daily_task_requires_output_file(self):
        config = {
            "ai": {
                "provider": "claude",
                "skill_enforcement": {"enabled": False},
            }
        }
        prefs = {"risk_level": "moderate"}
        with patch("ai_runner.run_ai_task", return_value=(True, "ok", "")):
            with patch("ai_runner._find_recent_output", return_value=None):
                success, _, stderr = ai_runner.run_tw_stock_analyzer(config, prefs)

        self.assertFalse(success)
        self.assertIn("未找到新產生的交易計畫檔案", stderr)

    def test_monitor_task_requires_output_file(self):
        config = {
            "ai": {
                "provider": "claude",
                "retry": {"max_attempts": 1, "backoff_seconds": 0},
                "skill_enforcement": {"enabled": False},
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(ai_runner, "INTRADAY_DIR", temp_dir):
                with patch("ai_runner.run_ai_task", return_value=(True, "ok", "")):
                    with patch("ai_runner._find_recent_intraday_report", return_value=None):
                        success, _, stderr = ai_runner.run_single_stock_analysis("2330", config)

        self.assertFalse(success)
        self.assertIn("未找到新產生的個股分析檔案", stderr)

    # 2026-02-14 調整方式: 新增 monitor multi-stock 輸出解析失敗測試。
    def test_run_multi_stock_analysis_requires_valid_json_output(self):
        config = {
            "ai": {
                "provider": "claude",
                "skill_enforcement": {"enabled": False},
            }
        }

        with patch("ai_runner.run_ai_task", return_value=(True, "not-json", "")):
            success, results, stderr = ai_runner.run_multi_stock_analysis(["2330", "2317"], config)

        self.assertFalse(success)
        self.assertEqual(results, [])
        self.assertIn("無法解析 JSON", stderr)

    # 2026-02-14 調整方式: 新增 monitor multi-stock 部分成功流程測試。
    def test_run_multi_stock_analysis_partial_success_should_return_true(self):
        config = {
            "ai": {
                "provider": "claude",
                "skill_enforcement": {"enabled": False},
            }
        }
        stdout_payload = {
            "error": False,
            "message": "批次分析完成：成功 1 檔，失敗 1 檔。",
            "results": [
                {
                    "stock_code": "2330",
                    "stock_name": "台積電",
                    "price": {"close": 1000.5},
                    "suggestion": "buy",
                    "score": 3,
                    "bullish_signals": ["MA5上穿MA20"],
                    "bearish_signals": [],
                }
            ],
            "failed_symbols": [
                {
                    "input": "BAD",
                    "resolved_code": "",
                    "reason": "無法辨識股票代號或名稱",
                }
            ],
        }
        stdout = json.dumps(stdout_payload, ensure_ascii=False)

        with patch("ai_runner.run_ai_task", return_value=(True, stdout, "partial")):
            success, results, stderr = ai_runner.run_multi_stock_analysis(["2330", "BAD"], config)

        self.assertTrue(success)
        self.assertEqual(stderr, "partial")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["stock_code"], "2330")
        self.assertEqual(results[0]["stock_name"], "台積電")
        self.assertEqual(results[0]["price"], 1000.5)
        self.assertEqual(results[0]["bullish_count"], 1)
        self.assertEqual(results[0]["bearish_count"], 0)

    # 2026-02-14 調整方式: monitor 強制 skill 改為 multi-stock-analyzer。
    def test_monitor_multi_stock_task_injects_skill_prompt_when_enforced(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_skills_dir = os.path.join(temp_dir, "repo_skills")
            self._create_skill_dir(repo_skills_dir, "multi-stock-analyzer")
            stdout_payload = {
                "error": False,
                "message": "ok",
                "results": [
                    {
                        "stock_code": "2330",
                        "stock_name": "台積電",
                        "price": {"close": 1000},
                        "suggestion": "watch",
                        "score": 0,
                        "bullish_signals": [],
                        "bearish_signals": [],
                    }
                ],
                "failed_symbols": [],
            }
            stdout = json.dumps(stdout_payload, ensure_ascii=False)

            config = {
                "ai": {
                    "provider": "claude",
                    "skill_enforcement": {
                        "enabled": True,
                        "mode": "strict",
                        "repo_skill_roots": [repo_skills_dir],
                        "task_skill_map": {"monitor": "multi-stock-analyzer"},
                        "provider_home_map": {
                            "claude": os.path.join(temp_dir, "home_skills")
                        },
                    },
                }
            }

            with patch("ai_runner.run_ai_task", return_value=(True, stdout, "")) as mock_run:
                success, results, _ = ai_runner.run_multi_stock_analysis(
                    ["2330", "2317"],
                    config,
                )

        self.assertTrue(success)
        self.assertEqual(len(results), 1)
        run_call_args = mock_run.call_args.args
        injected_prompt = run_call_args[1]
        self.assertIn("【Skill 強制規則】", injected_prompt)
        self.assertIn("本次任務必須使用 skill：multi-stock-analyzer", injected_prompt)
        self.assertIn("2330 2317", injected_prompt)

    def test_monitor_task_strict_missing_skill_should_fail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "ai": {
                    "provider": "claude",
                    "skill_enforcement": {
                        "enabled": True,
                        "mode": "strict",
                        "repo_skill_roots": [os.path.join(temp_dir, "repo_skills")],
                        "task_skill_map": {"monitor": "single-stock-analyzer"},
                        "provider_home_map": {
                            "claude": os.path.join(temp_dir, "home_skills")
                        },
                    },
                }
            }

            with patch("ai_runner.run_ai_task") as mock_run:
                success, _, stderr = ai_runner.run_single_stock_analysis("2330", config)

        self.assertFalse(success)
        self.assertIn("缺少必要 skill", stderr)
        mock_run.assert_not_called()

    def test_monitor_task_injects_skill_prompt_when_enforced(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            intraday_dir = os.path.join(temp_dir, "intraday")
            report_path = os.path.join(intraday_dir, "stock_analysis_2330_20260214.md")
            markdown_content = (
                "---\n"
                "stock_code: 2330\n"
                "stock_name: 台積電\n"
                "suggestion: buy\n"
                "score: 3\n"
                "bullish_signals: [\"MA5上穿MA20\"]\n"
                "bearish_signals: []\n"
                "price_close: 1000\n"
                "---\n"
            )
            repo_skills_dir = os.path.join(temp_dir, "repo_skills")
            self._create_skill_dir(repo_skills_dir, "single-stock-analyzer")

            config = {
                "ai": {
                    "provider": "claude",
                    "skill_enforcement": {
                        "enabled": True,
                        "mode": "strict",
                        "repo_skill_roots": [repo_skills_dir],
                        "task_skill_map": {"monitor": "single-stock-analyzer"},
                        "provider_home_map": {
                            "claude": os.path.join(temp_dir, "home_skills")
                        },
                    },
                }
            }

            with patch.object(ai_runner, "INTRADAY_DIR", intraday_dir):
                with patch("ai_runner.run_ai_task", return_value=(True, "ok", "")) as mock_run:
                    with patch(
                        "ai_runner._find_recent_intraday_report",
                        return_value=report_path,
                    ):
                        with patch("ai_runner.open", mock_open(read_data=markdown_content)):
                            success, stdout, _ = ai_runner.run_single_stock_analysis(
                                "2330",
                                config,
                            )

        self.assertTrue(success)
        self.assertIn("stock_code: 2330", stdout)
        run_call_args = mock_run.call_args.args
        injected_prompt = run_call_args[1]
        self.assertIn("【Skill 強制規則】", injected_prompt)
        self.assertIn("本次任務必須使用 skill：single-stock-analyzer", injected_prompt)

    def test_news_task_strict_missing_skill_should_fail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "ai": {
                    "provider": "claude",
                    "skill_enforcement": {
                        "enabled": True,
                        "mode": "strict",
                        "repo_skill_roots": [os.path.join(temp_dir, "repo_skills")],
                        "task_skill_map": {"news": "news-stock-picker"},
                        "provider_home_map": {
                            "claude": os.path.join(temp_dir, "home_skills")
                        },
                    },
                }
            }

            with patch("ai_runner.run_ai_task") as mock_run:
                success, _, stderr = ai_runner.run_news_stock_picker(config)

        self.assertFalse(success)
        self.assertIn("缺少必要 skill", stderr)
        mock_run.assert_not_called()

    def test_news_task_injects_skill_prompt_when_enforced(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_skills_dir = os.path.join(temp_dir, "repo_skills")
            self._create_skill_dir(repo_skills_dir, "news-stock-picker")

            config = {
                "ai": {
                    "provider": "claude",
                    "skill_enforcement": {
                        "enabled": True,
                        "mode": "strict",
                        "repo_skill_roots": [repo_skills_dir],
                        "task_skill_map": {"news": "news-stock-picker"},
                        "provider_home_map": {
                            "claude": os.path.join(temp_dir, "home_skills")
                        },
                    },
                }
            }

            with patch("ai_runner.run_ai_task", return_value=(True, "ok", "")) as mock_run:
                with patch("ai_runner._find_recent_output", return_value="/tmp/report.md"):
                    success, _, _ = ai_runner.run_news_stock_picker(config)

        self.assertTrue(success)
        run_call_args = mock_run.call_args.args
        injected_prompt = run_call_args[1]
        self.assertIn("【Skill 強制規則】", injected_prompt)
        self.assertIn("本次任務必須使用 skill：news-stock-picker", injected_prompt)

    def test_news_task_warn_mode_fallback_to_plain_prompt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "ai": {
                    "provider": "claude",
                    "skill_enforcement": {
                        "enabled": True,
                        "mode": "warn",
                        "repo_skill_roots": [os.path.join(temp_dir, "repo_skills")],
                        "task_skill_map": {"news": "news-stock-picker"},
                        "provider_home_map": {
                            "claude": os.path.join(temp_dir, "home_skills")
                        },
                    },
                }
            }

            with patch("ai_runner.run_ai_task", return_value=(True, "ok", "")) as mock_run:
                with patch("ai_runner._find_recent_output", return_value="/tmp/report.md"):
                    success, _, _ = ai_runner.run_news_stock_picker(config)

        self.assertTrue(success)
        run_call_args = mock_run.call_args.args
        prompt = run_call_args[1]
        self.assertNotIn("【Skill 強制規則】", prompt)

    # 2026-02-13 調整方式: 驗證 repo roots 缺 skill 時，會 fallback 使用 provider home。
    def test_news_task_strict_uses_provider_home_skill_as_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home_skills_dir = os.path.join(temp_dir, "home_skills")
            skill_dir = self._create_skill_dir(home_skills_dir, "news-stock-picker")

            config = {
                "ai": {
                    "provider": "claude",
                    "skill_enforcement": {
                        "enabled": True,
                        "mode": "strict",
                        "repo_skill_roots": [os.path.join(temp_dir, "repo_skills")],
                        "task_skill_map": {"news": "news-stock-picker"},
                        "provider_home_map": {
                            "claude": home_skills_dir
                        },
                    },
                }
            }

            with patch("ai_runner.run_ai_task", return_value=(True, "ok", "")) as mock_run:
                with patch("ai_runner._find_recent_output", return_value="/tmp/report.md"):
                    success, _, _ = ai_runner.run_news_stock_picker(config)

        self.assertTrue(success)
        run_call_args = mock_run.call_args.args
        injected_prompt = run_call_args[1]
        self.assertIn("【Skill 強制規則】", injected_prompt)
        self.assertIn(f"專案 skill 路徑：{skill_dir}", injected_prompt)

    # 2026-02-13 調整方式: 驗證來源與目標同路徑時，不會執行自刪除或重複 copy。
    def test_sync_repo_skills_source_equals_target_should_skip_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home_skills_dir = os.path.join(temp_dir, "home_skills")
            skill_dir = self._create_skill_dir(home_skills_dir, "news-stock-picker")
            skill_cfg = {
                "enabled": True,
                "mode": "strict",
                "repo_skill_roots": [home_skills_dir],
                "task_skill_map": {"news": "news-stock-picker"},
                "provider_home_map": {
                    "claude": home_skills_dir
                },
            }

            synced_skill_map, sync_error = ai_runner._sync_repo_skills_to_provider_home(
                "claude", skill_cfg
            )

        self.assertEqual(sync_error, "")
        self.assertEqual(
            synced_skill_map.get("news-stock-picker"),
            skill_dir,
        )


if __name__ == "__main__":
    unittest.main()
