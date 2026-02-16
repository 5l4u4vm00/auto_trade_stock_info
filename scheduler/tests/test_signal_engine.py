import unittest

from scheduler.services.risk_rules import apply_risk_rules
from scheduler.services.signal_engine import (
    build_daily_candidates_from_plan,
    build_intraday_candidates_from_results,
)


class SignalEngineTest(unittest.TestCase):
    def test_build_daily_candidates_from_plan(self):
        parsed_plan = {
            "buy_candidates": ["2330", "2317"],
            "watchlist": ["2454"],
        }

        candidates = build_daily_candidates_from_plan(parsed_plan)

        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[0].action, "buy")
        self.assertEqual(candidates[-1].action, "watch")

    def test_build_intraday_candidates_from_results(self):
        parsed_results = [
            {
                "stock_code": "2330",
                "stock_name": "台積電",
                "score": 5,
                "bullish_count": 4,
                "bearish_count": 1,
                "bullish_signals": ["ma_cross"],
                "bearish_signals": [],
                "suggestion": "buy",
                "price": 1200,
            }
        ]

        candidates = build_intraday_candidates_from_results(parsed_results)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].stock_code, "2330")
        self.assertEqual(candidates[0].action, "buy")
        self.assertGreater(candidates[0].total_score, 0)

    def test_apply_risk_rules_limit_buy_signal_count(self):
        parsed_plan = {
            "buy_candidates": ["2330", "2317", "2454"],
            "watchlist": [],
        }
        candidates = build_daily_candidates_from_plan(parsed_plan)

        adjusted_candidates = apply_risk_rules(
            candidates,
            {
                "capital": 100000,
                "max_buy_signals": 1,
                "min_buy_confidence": 0.1,
            },
        )

        buy_actions = [item for item in adjusted_candidates if item.action == "buy"]
        self.assertEqual(len(buy_actions), 1)


if __name__ == "__main__":
    unittest.main()
