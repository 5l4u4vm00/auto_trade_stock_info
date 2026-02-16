import tempfile
import unittest
from pathlib import Path

from scheduler.domain.types import CandidateSignal
from scheduler.reporting.report_writer import (
    write_candidates_json,
    write_candidates_markdown,
)


class ReportWriterTest(unittest.TestCase):
    def test_write_candidates_json_and_markdown(self):
        candidate = CandidateSignal(
            stock_code="2330",
            signal_date="2026-02-15",
            technical_score=66.2,
            news_score=0,
            risk_penalty=2,
            total_score=64.2,
            action="buy",
            confidence=0.66,
            reasons=["test"],
            source="unit_test",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "signals.json"
            md_path = Path(temp_dir) / "signals.md"

            write_candidates_json([candidate], json_path, {"job": "daily"})
            write_candidates_markdown([candidate], md_path, {"job": "daily"})

            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            self.assertIn("2330", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
