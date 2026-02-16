"""每日交易計畫任務。"""

import logging
import os
import time
from datetime import date, datetime
from pathlib import Path

try:
    from ai_runner import run_tw_stock_analyzer
    from ai_runner import find_latest_trading_plan
    from email_sender import EmailSender
    from report_parser import parse_trading_plan
    from services.risk_rules import apply_risk_rules
    from services.signal_engine import build_daily_candidates_from_plan
    from trading_calendar import is_trading_day
except ModuleNotFoundError:  # pragma: no cover
    from scheduler.ai_runner import run_tw_stock_analyzer  # type: ignore
    from scheduler.ai_runner import find_latest_trading_plan  # type: ignore
    from scheduler.email_sender import EmailSender  # type: ignore
    from scheduler.report_parser import parse_trading_plan  # type: ignore
    from scheduler.services.risk_rules import apply_risk_rules  # type: ignore
    from scheduler.services.signal_engine import build_daily_candidates_from_plan  # type: ignore
    from scheduler.trading_calendar import is_trading_day  # type: ignore

from .common import _build_run_id, _log_job_event, _write_candidate_outputs

logger = logging.getLogger("scheduler")


def job_daily_analysis(config):
    """交易日執行台股分析。"""
    # 2026-02-15 調整方式: 從 main.py 拆分 daily 任務，保留候選訊號與寄信流程。
    started_at = time.time()
    run_id = _build_run_id("daily")
    today = date.today()

    if not is_trading_day(today):
        logger.info(f"今日 ({today.isoformat()}) 非交易日，跳過每日分析")
        _log_job_event(
            "daily",
            run_id,
            "skipped",
            run_date=today.isoformat(),
            reason="non_trading_day",
        )
        return

    logger.info("=" * 60)
    logger.info("Job 2: 開始執行每日台股分析")
    logger.info("=" * 60)

    prefs = config.get("trading_preferences", {})
    _log_job_event(
        "daily",
        run_id,
        "start",
        run_date=today.isoformat(),
        input_summary={
            "risk_level": prefs.get("risk_level", ""),
            "capital": prefs.get("capital", 0),
        },
    )

    try:
        success, _, stderr = run_tw_stock_analyzer(config, prefs)

        if not success:
            logger.error(f"台股分析執行失敗: {stderr[:500]}")
            _log_job_event(
                "daily",
                run_id,
                "failed",
                duration_sec=round(time.time() - started_at, 2),
                error_code="ai_task_failed",
            )
            return

        report_path = find_latest_trading_plan(today)
        if report_path and os.path.exists(report_path):
            report_content = Path(report_path).read_text(encoding="utf-8")
            logger.info(f"交易計畫已產生: {report_path}")

            parsed = parse_trading_plan(report_path)
            logger.info(
                f"推薦股票: 買進 {parsed['buy_candidates']}, 觀察 {parsed['watchlist']}"
            )

            daily_candidates = build_daily_candidates_from_plan(parsed, today)
            risk_adjusted_candidates = apply_risk_rules(daily_candidates, prefs)
            candidate_files = _write_candidate_outputs(
                "daily",
                run_id,
                datetime.now(),
                risk_adjusted_candidates,
            )

            email_sender = EmailSender(config["email"])
            email_sender.send_report(
                subject=f"[台股日報] 每日交易計畫 {today.isoformat()}",
                body=report_content,
                attachments=[report_path, *candidate_files],
            )
            _log_job_event(
                "daily",
                run_id,
                "completed",
                duration_sec=round(time.time() - started_at, 2),
                output_files=[report_path, *candidate_files],
                candidate_count=len(risk_adjusted_candidates),
            )
        else:
            logger.error("台股分析執行成功但找不到交易計畫檔案，視為失敗")
            _log_job_event(
                "daily",
                run_id,
                "failed",
                duration_sec=round(time.time() - started_at, 2),
                error_code="missing_report",
            )
            return

    except Exception as exc:  # pragma: no cover
        logger.exception(f"每日台股分析異常: {exc}")
        _log_job_event(
            "daily",
            run_id,
            "failed",
            duration_sec=round(time.time() - started_at, 2),
            error_code="exception",
            error_message=str(exc),
        )

    logger.info("Job 2: 每日台股分析完成")

