import unittest
from datetime import date

from scheduler.trading_calendar import is_trading_day


class TradingCalendarTest(unittest.TestCase):
    def test_is_trading_day_weekend(self):
        saturday = date(2026, 2, 14)
        self.assertFalse(is_trading_day(saturday))

    def test_is_trading_day_holiday(self):
        holiday = date(2026, 2, 18)
        self.assertFalse(is_trading_day(holiday))


if __name__ == "__main__":
    unittest.main()
