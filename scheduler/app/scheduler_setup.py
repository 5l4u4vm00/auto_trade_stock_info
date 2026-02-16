"""APScheduler 註冊流程。"""

import logging

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
except ModuleNotFoundError:  # pragma: no cover
    BackgroundScheduler = None
    CronTrigger = None

try:
    from jobs.daily_job import job_daily_analysis
    from jobs.monitor_job import job_intraday_monitor
    from jobs.news_job import job_news_stock_picker
except ModuleNotFoundError:  # pragma: no cover
    from scheduler.jobs.daily_job import job_daily_analysis  # type: ignore
    from scheduler.jobs.monitor_job import job_intraday_monitor  # type: ignore
    from scheduler.jobs.news_job import job_news_stock_picker  # type: ignore

logger = logging.getLogger("scheduler")


def setup_scheduler(config):
    """設定 APScheduler。"""
    # 2026-02-15 調整方式: 從 main.py 拆分排程註冊邏輯，保持 cron 行為不變。
    if BackgroundScheduler is None or CronTrigger is None:
        raise ModuleNotFoundError("apscheduler is required to setup scheduler jobs")

    scheduler = BackgroundScheduler()
    sched = config.get("schedule", {})

    day_map = {
        "mon": "mon",
        "tue": "tue",
        "wed": "wed",
        "thu": "thu",
        "fri": "fri",
        "sat": "sat",
        "sun": "sun",
    }
    news_day = day_map.get(sched.get("news_picker_day", "sun"), "sun")
    news_time = sched.get("news_picker_time", "00:00")
    news_h, news_m = map(int, news_time.split(":"))

    scheduler.add_job(
        job_news_stock_picker,
        CronTrigger(day_of_week=news_day, hour=news_h, minute=news_m),
        args=[config],
        id="news_stock_picker",
        name="每週新聞選股",
        misfire_grace_time=3600,
    )
    logger.info(f"Job 1 已設定: 每週{news_day} {news_time} 新聞選股")

    daily_time = sched.get("daily_analysis_time", "08:00")
    daily_h, daily_m = map(int, daily_time.split(":"))

    scheduler.add_job(
        job_daily_analysis,
        CronTrigger(day_of_week="mon-fri", hour=daily_h, minute=daily_m),
        args=[config],
        id="daily_analysis",
        name="每日台股分析",
        misfire_grace_time=3600,
    )
    logger.info(f"Job 2 已設定: 週一至週五 {daily_time} 每日分析")

    interval = sched.get("monitor_interval_minutes", 30)
    monitor_start = sched.get("monitor_start", "09:00")
    monitor_end = sched.get("monitor_end", "13:30")
    start_h, _ = map(int, monitor_start.split(":"))
    end_h, _ = map(int, monitor_end.split(":"))

    scheduler.add_job(
        job_intraday_monitor,
        CronTrigger(
            day_of_week="mon-fri",
            hour=f"{start_h}-{end_h}",
            minute=f"*/{interval}",
        ),
        args=[config],
        id="intraday_monitor",
        name="盤中即時監控",
        misfire_grace_time=600,
    )
    logger.info(
        f"Job 3 已設定: 週一至週五 {monitor_start}-{monitor_end} 每 {interval} 分鐘監控"
    )

    return scheduler
