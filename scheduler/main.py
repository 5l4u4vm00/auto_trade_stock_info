#!/usr/bin/env python3
"""
台股自動化排程分析系統 — 主排程程式

使用 APScheduler 管理三個排程任務：
  Job 1: 每週日新聞選股
  Job 2: 交易日每日台股分析
  Job 3: 交易日盤中即時監控

用法:
  python3 scheduler/main.py                  # 啟動排程
  python3 scheduler/main.py --test-email     # 測試 email
  python3 scheduler/main.py --test-job news  # 測試新聞選股
  python3 scheduler/main.py --test-job daily # 測試每日分析
  python3 scheduler/main.py --test-job monitor # 測試盤中監控
"""

import argparse
import atexit
import glob
import logging
import os
import signal
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

# 確保可以 import 同目錄模組
sys.path.insert(0, os.path.dirname(__file__))

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ai_runner import (
    run_news_stock_picker,
    run_tw_stock_analyzer,
    run_multi_stock_analysis,
    find_latest_news_report,
    find_latest_trading_plan,
)
from email_sender import EmailSender
from report_parser import parse_trading_plan, check_alert
from trading_calendar import is_trading_day

# ============================================================
# 路徑設定
# ============================================================
SCHEDULER_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCHEDULER_DIR, '..'))
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
PID_FILE = os.path.join(SCHEDULER_DIR, 'scheduler.pid')
CONFIG_FILE = os.path.join(SCHEDULER_DIR, 'config.yaml')
STRATEGY_DIR = os.path.join(PROJECT_ROOT, 'strategy')
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, 'outputs')

# ============================================================
# 日誌設定
# ============================================================
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'scheduler.log'), encoding='utf-8'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger('scheduler')


# ============================================================
# 設定檔讀取
# ============================================================
def load_config():
    """讀取 config.yaml"""
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"設定檔不存在: {CONFIG_FILE}")
        sys.exit(1)

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config


# ============================================================
# PID 管理
# ============================================================
def check_pid():
    """檢查是否已有排程程式在執行"""
    if os.path.exists(PID_FILE):
        with open(PID_FILE, 'r') as f:
            old_pid = f.read().strip()

        if old_pid:
            try:
                os.kill(int(old_pid), 0)
                logger.error(f"排程程式已在執行中 (PID={old_pid})，請先停止")
                sys.exit(1)
            except (ProcessLookupError, ValueError):
                # 舊 PID 已不存在，移除 PID 檔案
                os.remove(PID_FILE)


def write_pid():
    """寫入當前 PID"""
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))


def remove_pid():
    """移除 PID 檔案"""
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)


# ============================================================
# Job 1: 每週日新聞選股
# ============================================================
def job_news_stock_picker(config):
    """每週日執行新聞選股"""
    logger.info("=" * 60)
    logger.info("Job 1: 開始執行新聞選股")
    logger.info("=" * 60)

    today = date.today()

    try:
        success, stdout, stderr = run_news_stock_picker(config)

        if not success:
            logger.error(f"新聞選股執行失敗: {stderr[:500]}")
            return

        report_path = find_latest_news_report(today)
        if report_path:
            report_content = Path(report_path).read_text(encoding='utf-8')
            logger.info(f"新聞選股報告已產生: {report_path}")

            # Email 寄出
            email_sender = EmailSender(config['email'])
            email_sender.send_report(
                subject=f"[台股週報] 新聞選股策略 {today.isoformat()}",
                body=report_content,
                attachments=[report_path],
            )
        else:
            logger.error("新聞選股執行成功但找不到報告檔案，視為失敗")
            return

    except Exception as e:
        logger.exception(f"新聞選股執行異常: {e}")

    logger.info("Job 1: 新聞選股完成")


# ============================================================
# Job 2: 每日台股分析
# ============================================================
def job_daily_analysis(config):
    """交易日執行台股分析"""
    today = date.today()

    if not is_trading_day(today):
        logger.info(f"今日 ({today.isoformat()}) 非交易日，跳過每日分析")
        return

    logger.info("=" * 60)
    logger.info("Job 2: 開始執行每日台股分析")
    logger.info("=" * 60)

    prefs = config.get('trading_preferences', {})

    try:
        success, stdout, stderr = run_tw_stock_analyzer(config, prefs)

        if not success:
            logger.error(f"台股分析執行失敗: {stderr[:500]}")
            return

        report_path = find_latest_trading_plan(today)
        if report_path and os.path.exists(report_path):
            report_content = Path(report_path).read_text(encoding='utf-8')
            logger.info(f"交易計畫已產生: {report_path}")

            # 解析推薦股票
            parsed = parse_trading_plan(report_path)
            logger.info(f"推薦股票: 買進 {parsed['buy_candidates']}, 觀察 {parsed['watchlist']}")

            # Email 寄出
            email_sender = EmailSender(config['email'])
            email_sender.send_report(
                subject=f"[台股日報] 每日交易計畫 {today.isoformat()}",
                body=report_content,
                attachments=[report_path],
            )
        else:
            logger.error("台股分析執行成功但找不到交易計畫檔案，視為失敗")
            return

    except Exception as e:
        logger.exception(f"每日台股分析異常: {e}")

    logger.info("Job 2: 每日台股分析完成")


# ============================================================
# Job 3: 盤中即時監控
# ============================================================
def job_intraday_monitor(config):
    """交易日盤中監控"""
    today = date.today()
    now = datetime.now()

    if not is_trading_day(today):
        logger.info(f"今日 ({today.isoformat()}) 非交易日，跳過盤中監控")
        return

    # 確認在開盤時間內
    sched = config.get('schedule', {})
    monitor_start = sched.get('monitor_start', '09:00')
    monitor_end = sched.get('monitor_end', '13:30')

    start_h, start_m = map(int, monitor_start.split(':'))
    end_h, end_m = map(int, monitor_end.split(':'))
    start_time = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end_time = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

    if not (start_time <= now <= end_time):
        logger.info(f"目前時間 {now.strftime('%H:%M')} 不在監控時段 ({monitor_start}-{monitor_end})")
        return

    logger.info("=" * 60)
    logger.info(f"Job 3: 開始盤中監控 ({now.strftime('%H:%M')})")
    logger.info("=" * 60)

    # 讀取當日交易計畫，取得監控清單
    date_str = today.strftime('%Y%m%d')
    report_path = os.path.join(OUTPUTS_DIR, f"trading_plan_{date_str}.md")

    if not os.path.exists(report_path):
        # 嘗試尋找最新的
        all_plans = sorted(glob.glob(os.path.join(OUTPUTS_DIR, "trading_plan_*.md")))
        if all_plans:
            report_path = all_plans[-1]

    if not os.path.exists(report_path):
        logger.warning("找不到當日交易計畫，無法執行盤中監控")
        return

    parsed = parse_trading_plan(report_path)
    stock_list = parsed['all']

    if not stock_list:
        logger.info("當日無推薦股票，跳過盤中監控")
        return

    logger.info(f"監控清單: {stock_list}")

    # 2026-02-14 調整方式: monitor 改為 multi-stock 批次分析。
    threshold = config.get('signal_threshold', {})
    alerts = []

    logger.info(f"批次分析個股: {stock_list}")
    success, parsed_results, stderr = run_multi_stock_analysis(stock_list, config)
    if not success:
        logger.warning(f"批次個股分析失敗: {stderr[:200]}")
        return

    for result in parsed_results:
        alert = check_alert(result, threshold)
        if alert:
            alerts.append(alert)
            logger.info(f"觸發警報: {alert['stock_code']} {alert['stock_name']} "
                        f"({alert['signal_type']}) - {alert['reason']}")

    # 彙整警報並寄送
    if alerts:
        logger.info(f"共 {len(alerts)} 檔觸發警報，寄送 email")
        email_sender = EmailSender(config['email'])
        email_sender.send_alert(alerts)
    else:
        logger.info("本次監控無觸發警報")

    logger.info("Job 3: 盤中監控完成")


# ============================================================
# 排程設定
# ============================================================
def setup_scheduler(config):
    """設定 APScheduler"""
    scheduler = BackgroundScheduler()
    sched = config.get('schedule', {})

    # Job 1: 每週日新聞選股
    day_map = {'mon': 'mon', 'tue': 'tue', 'wed': 'wed', 'thu': 'thu',
               'fri': 'fri', 'sat': 'sat', 'sun': 'sun'}
    news_day = day_map.get(sched.get('news_picker_day', 'sun'), 'sun')
    news_time = sched.get('news_picker_time', '00:00')
    news_h, news_m = map(int, news_time.split(':'))

    scheduler.add_job(
        job_news_stock_picker,
        CronTrigger(day_of_week=news_day, hour=news_h, minute=news_m),
        args=[config],
        id='news_stock_picker',
        name='每週新聞選股',
        misfire_grace_time=3600,
    )
    logger.info(f"Job 1 已設定: 每週{news_day} {news_time} 新聞選股")

    # Job 2: 每日台股分析（週一至週五）
    daily_time = sched.get('daily_analysis_time', '08:00')
    daily_h, daily_m = map(int, daily_time.split(':'))

    scheduler.add_job(
        job_daily_analysis,
        CronTrigger(day_of_week='mon-fri', hour=daily_h, minute=daily_m),
        args=[config],
        id='daily_analysis',
        name='每日台股分析',
        misfire_grace_time=3600,
    )
    logger.info(f"Job 2 已設定: 週一至週五 {daily_time} 每日分析")

    # Job 3: 盤中即時監控（週一至週五，每 N 分鐘）
    interval = sched.get('monitor_interval_minutes', 30)
    monitor_start = sched.get('monitor_start', '09:00')
    monitor_end = sched.get('monitor_end', '13:30')
    start_h, start_m = map(int, monitor_start.split(':'))
    end_h, end_m = map(int, monitor_end.split(':'))

    scheduler.add_job(
        job_intraday_monitor,
        CronTrigger(
            day_of_week='mon-fri',
            hour=f'{start_h}-{end_h}',
            minute=f'*/{interval}',
        ),
        args=[config],
        id='intraday_monitor',
        name='盤中即時監控',
        misfire_grace_time=600,
    )
    logger.info(f"Job 3 已設定: 週一至週五 {monitor_start}-{monitor_end} 每 {interval} 分鐘監控")

    return scheduler


# ============================================================
# 主程式
# ============================================================
def main():
    parser = argparse.ArgumentParser(description='台股自動化排程分析系統')
    parser.add_argument('--test-email', action='store_true', help='測試 email 寄送')
    parser.add_argument('--test-job', choices=['news', 'daily', 'monitor'],
                        help='測試執行指定 job')
    args = parser.parse_args()

    config = load_config()

    # 測試 email
    if args.test_email:
        logger.info("測試 email 寄送...")
        email_sender = EmailSender(config['email'])
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
        return

    # 測試個別 job
    if args.test_job:
        logger.info(f"測試執行 job: {args.test_job}")
        if args.test_job == 'news':
            job_news_stock_picker(config)
        elif args.test_job == 'daily':
            job_daily_analysis(config)
        elif args.test_job == 'monitor':
            job_intraday_monitor(config)
        return

    # 正式啟動排程
    check_pid()
    write_pid()
    atexit.register(remove_pid)

    logger.info("=" * 60)
    logger.info("台股自動化排程分析系統啟動")
    logger.info(f"PID: {os.getpid()}")
    logger.info("=" * 60)

    scheduler = setup_scheduler(config)
    scheduler.start()

    # 列出所有排程
    logger.info("排程任務一覽:")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name}: 下次執行 {job.next_run_time}")

    # Graceful shutdown
    def shutdown(signum, frame):
        logger.info(f"收到信號 {signum}，正在關閉排程...")
        scheduler.shutdown(wait=False)
        remove_pid()
        logger.info("排程系統已關閉")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # 常駐等待
    print("\n排程系統已啟動，按 Ctrl+C 停止。\n")
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == '__main__':
    main()
