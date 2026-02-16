"""每週新聞選股任務。"""

import logging
import time
from datetime import date
from pathlib import Path

try:
    from ai_runner import run_news_stock_picker as execute_news_stock_picker
    from ai_runner import find_latest_news_report
    from email_sender import EmailSender
except ModuleNotFoundError:  # pragma: no cover
    from scheduler.ai_runner import run_news_stock_picker as execute_news_stock_picker  # type: ignore
    from scheduler.ai_runner import find_latest_news_report  # type: ignore
    from scheduler.email_sender import EmailSender  # type: ignore

from .common import _build_run_id, _log_job_event

logger = logging.getLogger("scheduler")


def job_news_stock_picker(config):
    """每週日執行新聞選股。"""
    # 2026-02-15 調整方式: 從 main.py 拆分新聞任務，保留既有行為與輸出。
    started_at = time.time()
    run_id = _build_run_id("news")

    logger.info("=" * 60)
    logger.info("Job 1: 開始執行新聞選股")
    logger.info("=" * 60)

    today = date.today()
    _log_job_event(
        "news",
        run_id,
        "start",
        run_date=today.isoformat(),
    )

    try:
        success, _, stderr = execute_news_stock_picker(config)

        if not success:
            logger.error(f"新聞選股執行失敗: {stderr[:500]}")
            _log_job_event(
                "news",
                run_id,
                "failed",
                duration_sec=round(time.time() - started_at, 2),
                error_code="ai_task_failed",
            )
            return

        report_path = find_latest_news_report(today)
        if report_path:
            report_content = Path(report_path).read_text(encoding="utf-8")
            logger.info(f"新聞選股報告已產生: {report_path}")

            email_sender = EmailSender(config["email"])
            email_sender.send_report(
                subject=f"[台股週報] 新聞選股策略 {today.isoformat()}",
                body=report_content,
                attachments=[report_path],
            )
            _log_job_event(
                "news",
                run_id,
                "completed",
                duration_sec=round(time.time() - started_at, 2),
                output_files=[report_path],
            )
        else:
            logger.error("新聞選股執行成功但找不到報告檔案，視為失敗")
            _log_job_event(
                "news",
                run_id,
                "failed",
                duration_sec=round(time.time() - started_at, 2),
                error_code="missing_report",
            )
            return

    except Exception as exc:  # pragma: no cover
        logger.exception(f"新聞選股執行異常: {exc}")
        _log_job_event(
            "news",
            run_id,
            "failed",
            duration_sec=round(time.time() - started_at, 2),
            error_code="exception",
            error_message=str(exc),
        )

    logger.info("Job 1: 新聞選股完成")

