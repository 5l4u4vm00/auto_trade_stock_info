import unittest
from unittest.mock import patch

from scheduler.jobs.daily_job import job_daily_analysis


class DailyJobTest(unittest.TestCase):
    def test_job_daily_analysis_non_trading_day_should_skip(self):
        with patch(
            "scheduler.jobs.daily_job.is_trading_day",
            return_value=False,
        ), patch(
            "scheduler.jobs.daily_job.run_tw_stock_analyzer",
        ) as mock_run_analyzer:
            job_daily_analysis({"trading_preferences": {}})

        mock_run_analyzer.assert_not_called()

    def test_job_daily_analysis_success_should_send_report(self):
        config = {
            "email": {"sender": "test@example.com"},
            "trading_preferences": {"capital": 100000, "risk_level": "moderate"},
        }

        with patch(
            "scheduler.jobs.daily_job.is_trading_day",
            return_value=True,
        ), patch(
            "scheduler.jobs.daily_job.run_tw_stock_analyzer",
            return_value=(True, "", ""),
        ), patch(
            "scheduler.jobs.daily_job.find_latest_trading_plan",
            return_value="/tmp/trading_plan_20260215.md",
        ), patch(
            "scheduler.jobs.daily_job.os.path.exists",
            return_value=True,
        ), patch(
            "scheduler.jobs.daily_job.Path.read_text",
            return_value="# trading plan",
        ), patch(
            "scheduler.jobs.daily_job.parse_trading_plan",
            return_value={
                "buy_candidates": ["2330"],
                "watchlist": ["2454"],
                "all": ["2330", "2454"],
            },
        ), patch(
            "scheduler.jobs.daily_job.build_daily_candidates_from_plan",
            return_value=["candidate"],
        ), patch(
            "scheduler.jobs.daily_job.apply_risk_rules",
            return_value=["risk_adjusted"],
        ), patch(
            "scheduler.jobs.daily_job._write_candidate_outputs",
            return_value=["/tmp/daily.json", "/tmp/daily.md"],
        ), patch(
            "scheduler.jobs.daily_job.EmailSender",
        ) as mock_email_sender:
            job_daily_analysis(config)

        mock_email_sender.return_value.send_report.assert_called_once()


if __name__ == "__main__":
    unittest.main()

