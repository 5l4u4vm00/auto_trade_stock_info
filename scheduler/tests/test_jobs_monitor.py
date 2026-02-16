import unittest
from datetime import datetime
from unittest.mock import patch

from scheduler.jobs.monitor_job import job_intraday_monitor


class MonitorJobTest(unittest.TestCase):
    def test_job_intraday_monitor_non_trading_day_should_skip(self):
        with patch(
            "scheduler.jobs.monitor_job.is_trading_day",
            return_value=False,
        ), patch(
            "scheduler.jobs.monitor_job.run_multi_stock_analysis",
        ) as mock_run_multi:
            job_intraday_monitor({})

        mock_run_multi.assert_not_called()

    def test_job_intraday_monitor_with_alert_should_send_email(self):
        config = {
            "email": {"sender": "test@example.com"},
            "schedule": {
                "monitor_start": "09:00",
                "monitor_end": "13:30",
            },
            "signal_threshold": {
                "min_bullish_signals": 3,
                "min_bearish_signals": 3,
            },
            "trading_preferences": {
                "capital": 200000,
                "monitor_buy_ratio": 0.2,
                "monitor_sell_ratio": 0.3,
            },
        }

        parsed_results = [
            {
                "stock_code": "2330",
                "stock_name": "台積電",
                "price": 1180,
                "suggestion": "buy",
                "score": 6,
                "bullish_count": 4,
                "bearish_count": 1,
                "bullish_signals": ["ma_cross"],
                "bearish_signals": [],
            }
        ]
        alert = {
            "stock_code": "2330",
            "stock_name": "台積電",
            "signal_type": "buy",
            "price": 1180,
            "reason": "buy signal",
        }
        enriched_alert = {
            **alert,
            "suggested_quantity": 33,
            "quantity_unit": "股",
            "quantity_note": "test",
        }

        with patch(
            "scheduler.jobs.monitor_job.is_trading_day",
            return_value=True,
        ), patch(
            "scheduler.jobs.monitor_job.datetime",
        ) as mock_datetime, patch(
            "scheduler.jobs.monitor_job.os.path.exists",
            return_value=True,
        ), patch(
            "scheduler.jobs.monitor_job.parse_trading_plan",
            return_value={"all": ["2330"]},
        ), patch(
            "scheduler.jobs.monitor_job.run_multi_stock_analysis",
            return_value=(True, parsed_results, ""),
        ), patch(
            "scheduler.jobs.monitor_job.build_intraday_candidates_from_results",
            return_value=[],
        ), patch(
            "scheduler.jobs.monitor_job.apply_risk_rules",
            return_value=[],
        ), patch(
            "scheduler.jobs.monitor_job._write_candidate_outputs",
            return_value=["/tmp/monitor.json"],
        ), patch(
            "scheduler.jobs.monitor_job.check_alert",
            return_value=alert,
        ), patch(
            "scheduler.jobs.monitor_job._attach_quantity_to_alert",
            return_value=enriched_alert,
        ), patch(
            "scheduler.jobs.monitor_job._load_positions_map",
            return_value={},
        ), patch(
            "scheduler.jobs.monitor_job.EmailSender",
        ) as mock_email_sender:
            mock_datetime.now.return_value = datetime(2026, 2, 15, 10, 0)
            job_intraday_monitor(config)

        mock_email_sender.return_value.send_alert.assert_called_once_with([enriched_alert])


if __name__ == "__main__":
    unittest.main()

