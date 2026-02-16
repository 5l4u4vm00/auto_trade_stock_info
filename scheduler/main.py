#!/usr/bin/env python3
"""
台股自動化排程分析系統 — 主排程程式

用法:
  python3 scheduler/main.py                  # 啟動排程
  python3 scheduler/main.py --test-email     # 測試 email
  python3 scheduler/main.py --test-job news  # 測試新聞選股
  python3 scheduler/main.py --test-job daily # 測試每日分析
  python3 scheduler/main.py --test-job monitor # 測試盤中監控
"""

import argparse
import atexit
import logging
import os
import signal
import sys
import time

# 確保可以 import 同目錄模組
sys.path.insert(0, os.path.dirname(__file__))

try:
    from app.config_runtime import load_config
    from app.pid_guard import check_pid, remove_pid, write_pid
    from app.scheduler_setup import setup_scheduler
    from email_sender import EmailSender
    from jobs.daily_job import job_daily_analysis
    from jobs.monitor_job import job_intraday_monitor
    from jobs.news_job import job_news_stock_picker
except ModuleNotFoundError:  # pragma: no cover
    from scheduler.app.config_runtime import load_config  # type: ignore
    from scheduler.app.pid_guard import check_pid, remove_pid, write_pid  # type: ignore
    from scheduler.app.scheduler_setup import setup_scheduler  # type: ignore
    from scheduler.email_sender import EmailSender  # type: ignore
    from scheduler.jobs.daily_job import job_daily_analysis  # type: ignore
    from scheduler.jobs.monitor_job import job_intraday_monitor  # type: ignore
    from scheduler.jobs.news_job import job_news_stock_picker  # type: ignore

SCHEDULER_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCHEDULER_DIR, ".."))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "scheduler.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("scheduler")


def _run_test_email(config):
    logger.info("測試 email 寄送...")
    email_sender = EmailSender(config["email"])
    if email_sender.test_connection():
        success = email_sender.send_report(
            subject="[測試] 台股排程系統 email 測試",
            body="這是一封測試郵件。\n如果你收到此郵件，表示 email 設定正確。\n\n"
            "台股自動化排程分析系統",
        )
        if success:
            print("Email 測試寄送成功！")
        else:
            print("Email 寄送失敗，請檢查設定。")
    else:
        print("SMTP 連線失敗，請檢查 config.yaml 中的 email 設定。")


def _run_test_job(job_name, config):
    logger.info(f"測試執行 job: {job_name}")
    if job_name == "news":
        job_news_stock_picker(config)
        return
    if job_name == "daily":
        job_daily_analysis(config)
        return
    if job_name == "monitor":
        job_intraday_monitor(config)


def _bind_shutdown_signals(scheduler):
    def shutdown(signum, frame):
        logger.info(f"收到信號 {signum}，正在關閉排程...")
        scheduler.shutdown(wait=False)
        remove_pid()
        logger.info("排程系統已關閉")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)


def main():
    # 2026-02-15 調整方式: main.py 精簡為入口協調層，業務邏輯改由 app/jobs 模組處理。
    parser = argparse.ArgumentParser(description="台股自動化排程分析系統")
    parser.add_argument("--test-email", action="store_true", help="測試 email 寄送")
    parser.add_argument(
        "--test-job", choices=["news", "daily", "monitor"], help="測試執行指定 job"
    )
    args = parser.parse_args()
    config = load_config()

    if args.test_email:
        _run_test_email(config)
        return

    if args.test_job:
        _run_test_job(args.test_job, config)
        return

    check_pid()
    write_pid()
    atexit.register(remove_pid)

    logger.info("=" * 60)
    logger.info("台股自動化排程分析系統啟動")
    logger.info(f"PID: {os.getpid()}")
    logger.info("=" * 60)

    scheduler = setup_scheduler(config)
    scheduler.start()

    logger.info("排程任務一覽:")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name}: 下次執行 {job.next_run_time}")

    _bind_shutdown_signals(scheduler)

    print("\n排程系統已啟動，按 Ctrl+C 停止。\n")
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()

