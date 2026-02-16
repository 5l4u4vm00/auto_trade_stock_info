import unittest
from unittest.mock import patch

from scheduler.jobs.news_job import job_news_stock_picker


class NewsJobTest(unittest.TestCase):
    def test_job_news_stock_picker_missing_report_should_not_send_email(self):
        config = {"email": {"sender": "test@example.com"}}

        with patch(
            "scheduler.jobs.news_job.execute_news_stock_picker",
            return_value=(True, "", ""),
        ), patch(
            "scheduler.jobs.news_job.find_latest_news_report",
            return_value="",
        ), patch(
            "scheduler.jobs.news_job.EmailSender",
        ) as mock_email_sender:
            job_news_stock_picker(config)

        mock_email_sender.assert_not_called()

    def test_job_news_stock_picker_success_should_send_email(self):
        config = {"email": {"sender": "test@example.com"}}
        fake_report_path = "/tmp/news_strategy_20260215.md"

        with patch(
            "scheduler.jobs.news_job.execute_news_stock_picker",
            return_value=(True, "", ""),
        ), patch(
            "scheduler.jobs.news_job.find_latest_news_report",
            return_value=fake_report_path,
        ), patch(
            "scheduler.jobs.news_job.Path.read_text",
            return_value="# report",
        ), patch(
            "scheduler.jobs.news_job.EmailSender",
        ) as mock_email_sender:
            job_news_stock_picker(config)

        mock_email_sender.return_value.send_report.assert_called_once()


if __name__ == "__main__":
    unittest.main()

