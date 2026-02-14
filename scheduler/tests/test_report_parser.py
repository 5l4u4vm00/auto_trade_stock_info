import os
import sys
import unittest

SCHEDULER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCHEDULER_DIR not in sys.path:
    sys.path.insert(0, SCHEDULER_DIR)

import report_parser  # noqa: E402


class TestReportParser(unittest.TestCase):
    def test_parse_single_stock_markdown_frontmatter(self):
        markdown_text = """---
stock_code: "2330"
stock_name: "台積電"
suggestion: "BUY"
score: 4
bullish_signals:
  - MA5上穿MA20
  - MACD翻正
bearish_signals:
  - RSI過熱
price_close: 1025.5
---
# 報告
"""

        parsed = report_parser.parse_single_stock_result(markdown_text)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["stock_code"], "2330")
        self.assertEqual(parsed["suggestion"], "buy")
        self.assertEqual(parsed["score"], 4)
        self.assertEqual(parsed["bullish_count"], 2)
        self.assertEqual(parsed["bearish_count"], 1)
        self.assertEqual(parsed["price"], 1025.5)

    def test_parse_single_stock_markdown_missing_required_fields(self):
        markdown_text = """---
stock_code: "2330"
stock_name: "台積電"
---
# 報告
"""
        parsed = report_parser.parse_single_stock_result(markdown_text)
        self.assertIsNone(parsed)

    def test_parse_single_stock_json_compatibility(self):
        json_text = (
            '{"stock_code":"2317","stock_name":"鴻海","price":{"close":198.5},'
            '"suggestion":"watch","score":1,"bullish_signals":["A"],"bearish_signals":[]}'
        )
        parsed = report_parser.parse_single_stock_result(json_text)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["stock_code"], "2317")
        self.assertEqual(parsed["price"], 198.5)
        self.assertEqual(parsed["suggestion"], "watch")
        self.assertEqual(parsed["bullish_count"], 1)
        self.assertEqual(parsed["bearish_count"], 0)


if __name__ == "__main__":
    unittest.main()
