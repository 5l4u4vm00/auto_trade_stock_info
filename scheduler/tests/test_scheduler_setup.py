import unittest
from unittest.mock import patch

from scheduler.app.scheduler_setup import setup_scheduler


class DummyScheduler:
    def __init__(self):
        self.calls = []

    def add_job(self, *args, **kwargs):
        self.calls.append((args, kwargs))


class SchedulerSetupTest(unittest.TestCase):
    def test_setup_scheduler_should_register_three_jobs(self):
        config = {
            "schedule": {
                "news_picker_day": "sun",
                "news_picker_time": "00:00",
                "daily_analysis_time": "08:00",
                "monitor_start": "09:00",
                "monitor_end": "13:30",
                "monitor_interval_minutes": 10,
            }
        }
        dummy_scheduler = DummyScheduler()

        with patch(
            "scheduler.app.scheduler_setup.BackgroundScheduler",
            return_value=dummy_scheduler,
        ), patch(
            "scheduler.app.scheduler_setup.CronTrigger",
            side_effect=lambda **kwargs: kwargs,
        ):
            result = setup_scheduler(config)

        self.assertIs(result, dummy_scheduler)
        self.assertEqual(len(dummy_scheduler.calls), 3)

        job_ids = [call[1]["id"] for call in dummy_scheduler.calls]
        self.assertIn("news_stock_picker", job_ids)
        self.assertIn("daily_analysis", job_ids)
        self.assertIn("intraday_monitor", job_ids)


if __name__ == "__main__":
    unittest.main()
