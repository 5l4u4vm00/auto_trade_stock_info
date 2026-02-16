import unittest

from scheduler.report_parser import check_alert, parse_single_stock_result


class ReportParserTest(unittest.TestCase):
    def test_parse_single_stock_markdown_frontmatter(self):
        raw_text = """---
stock_code: "2330"
stock_name: "台積電"
suggestion: "buy"
score: 6
bullish_signals:
  - ma_cross
bearish_signals: []
price_close: 1180
---
# content
"""

        parsed = parse_single_stock_result(raw_text)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["stock_code"], "2330")
        self.assertEqual(parsed["suggestion"], "buy")

    def test_check_alert_with_buy_suggestion(self):
        parsed = {
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

        alert = check_alert(parsed, {"min_bullish_signals": 3, "min_bearish_signals": 3})

        self.assertIsNotNone(alert)
        self.assertEqual(alert["signal_type"], "buy")


if __name__ == "__main__":
    unittest.main()
