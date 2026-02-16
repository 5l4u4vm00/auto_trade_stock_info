"""盤中監控任務。"""

import glob
import json
import logging
import os
import time
from datetime import date, datetime

try:
    from ai_runner import run_multi_stock_analysis
    from email_sender import EmailSender
    from report_parser import check_alert, parse_trading_plan
    from services.risk_rules import apply_risk_rules
    from services.signal_engine import build_intraday_candidates_from_results
    from trading_calendar import is_trading_day
except ModuleNotFoundError:  # pragma: no cover
    from scheduler.ai_runner import run_multi_stock_analysis  # type: ignore
    from scheduler.email_sender import EmailSender  # type: ignore
    from scheduler.report_parser import check_alert, parse_trading_plan  # type: ignore
    from scheduler.services.risk_rules import apply_risk_rules  # type: ignore
    from scheduler.services.signal_engine import build_intraday_candidates_from_results  # type: ignore
    from scheduler.trading_calendar import is_trading_day  # type: ignore

from .common import (
    OUTPUTS_DIR,
    _build_run_id,
    _log_job_event,
    _write_candidate_outputs,
)

logger = logging.getLogger("scheduler")


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_ratio(value, default_ratio):
    ratio = _to_float(value, default_ratio)
    if ratio > 1:
        ratio = ratio / 100

    if ratio < 0:
        return 0.0
    if ratio > 1:
        return 1.0
    return ratio


def _load_positions_map():
    holdings_path = os.path.join(OUTPUTS_DIR, "current_holdings.json")
    if not os.path.exists(holdings_path):
        return {}

    try:
        with open(holdings_path, "r", encoding="utf-8") as file_obj:
            payload = json.load(file_obj)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"讀取 current_holdings 失敗，賣出建議量將使用 0: {exc}")
        return {}

    if not isinstance(payload, dict):
        return {}

    positions = payload.get("positions", [])
    if not isinstance(positions, list):
        return {}

    positions_map = {}
    for position in positions:
        if not isinstance(position, dict):
            continue

        stock_code = str(position.get("stock_code", "")).strip()
        if not stock_code:
            continue

        try:
            quantity = int(float(position.get("quantity", 0)))
        except (TypeError, ValueError):
            continue

        if quantity <= 0:
            continue

        positions_map[stock_code] = positions_map.get(stock_code, 0) + quantity

    return positions_map


def _calculate_buy_quantity(capital, buy_ratio, price):
    if capital <= 0 or buy_ratio <= 0 or price <= 0:
        return 0

    budget = capital * buy_ratio
    if budget < price:
        return 0

    return int(budget / price)


def _calculate_sell_quantity(holding_quantity, sell_ratio):
    if holding_quantity <= 0 or sell_ratio <= 0:
        return 0

    suggested_quantity = int(holding_quantity * sell_ratio)
    if suggested_quantity < 1:
        suggested_quantity = 1
    if suggested_quantity > holding_quantity:
        suggested_quantity = holding_quantity
    return suggested_quantity


def _attach_quantity_to_alert(
    alert,
    capital,
    buy_ratio,
    sell_ratio,
    positions_map,
):
    if not alert:
        return alert

    # 2026-02-15 調整方式: 從 main.py 拆分 monitor 數量計算並保留原始欄位契約。
    enriched_alert = dict(alert)
    stock_code = str(enriched_alert.get("stock_code", "")).strip()
    signal_type = str(enriched_alert.get("signal_type", "")).strip().lower()
    price = _to_float(enriched_alert.get("price", 0), 0.0)

    suggested_quantity = 0
    quantity_note = "不支援的訊號類型"

    if signal_type == "buy":
        suggested_quantity = _calculate_buy_quantity(capital, buy_ratio, price)
        if suggested_quantity > 0:
            quantity_note = (
                f"可用資金{capital:.0f} x 買入比例{buy_ratio:.0%} / 現價{price:.2f}"
            )
        else:
            quantity_note = "可用資金不足或現價異常，建議買入 0 股"
    elif signal_type == "sell":
        holding_quantity = positions_map.get(stock_code, 0)
        suggested_quantity = _calculate_sell_quantity(holding_quantity, sell_ratio)
        if holding_quantity > 0:
            quantity_note = f"持倉{holding_quantity}股 x 賣出比例{sell_ratio:.0%}"
        else:
            quantity_note = "查無持倉資料，建議賣出 0 股"

    enriched_alert["suggested_quantity"] = suggested_quantity
    enriched_alert["quantity_unit"] = "股"
    enriched_alert["quantity_note"] = quantity_note
    return enriched_alert


def job_intraday_monitor(config):
    """交易日盤中監控。"""
    started_at = time.time()
    run_id = _build_run_id("monitor")
    today = date.today()
    now = datetime.now()

    if not is_trading_day(today):
        logger.info(f"今日 ({today.isoformat()}) 非交易日，跳過盤中監控")
        _log_job_event(
            "monitor",
            run_id,
            "skipped",
            run_date=today.isoformat(),
            reason="non_trading_day",
        )
        return

    sched = config.get("schedule", {})
    monitor_start = sched.get("monitor_start", "09:00")
    monitor_end = sched.get("monitor_end", "13:30")

    start_h, start_m = map(int, monitor_start.split(":"))
    end_h, end_m = map(int, monitor_end.split(":"))
    start_time = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end_time = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

    if not (start_time <= now <= end_time):
        logger.info(
            f"目前時間 {now.strftime('%H:%M')} 不在監控時段 ({monitor_start}-{monitor_end})"
        )
        _log_job_event(
            "monitor",
            run_id,
            "skipped",
            run_time=now.strftime("%H:%M"),
            reason="outside_monitor_window",
        )
        return

    logger.info("=" * 60)
    logger.info(f"Job 3: 開始盤中監控 ({now.strftime('%H:%M')})")
    logger.info("=" * 60)
    _log_job_event(
        "monitor",
        run_id,
        "start",
        run_date=today.isoformat(),
        run_time=now.strftime("%H:%M"),
    )

    date_str = today.strftime("%Y%m%d")
    report_path = os.path.join(OUTPUTS_DIR, f"trading_plan_{date_str}.md")

    if not os.path.exists(report_path):
        all_plans = sorted(glob.glob(os.path.join(OUTPUTS_DIR, "trading_plan_*.md")))
        if all_plans:
            report_path = all_plans[-1]

    if not os.path.exists(report_path):
        logger.warning("找不到當日交易計畫，無法執行盤中監控")
        _log_job_event(
            "monitor",
            run_id,
            "failed",
            duration_sec=round(time.time() - started_at, 2),
            error_code="missing_daily_plan",
        )
        return

    parsed = parse_trading_plan(report_path)
    stock_list = parsed["all"]

    if not stock_list:
        logger.info("當日無推薦股票，跳過盤中監控")
        _log_job_event(
            "monitor",
            run_id,
            "skipped",
            duration_sec=round(time.time() - started_at, 2),
            reason="empty_stock_list",
        )
        return

    logger.info(f"監控清單: {stock_list}")

    threshold = config.get("signal_threshold", {})
    prefs = config.get("trading_preferences", {})
    capital = _to_float(prefs.get("capital", 0), 0)
    buy_ratio = _normalize_ratio(prefs.get("monitor_buy_ratio", 0.2), 0.2)
    sell_ratio = _normalize_ratio(prefs.get("monitor_sell_ratio", 0.3), 0.3)
    positions_map = _load_positions_map()
    alerts = []

    logger.info(
        f"盤中數量策略: 買入比例={buy_ratio:.0%}, 賣出比例={sell_ratio:.0%}, "
        f"可用資金={capital:.0f}"
    )

    logger.info(f"批次分析個股: {stock_list}")
    success, parsed_results, stderr = run_multi_stock_analysis(stock_list, config)
    if not success:
        logger.warning(f"批次個股分析失敗: {stderr[:200]}")
        _log_job_event(
            "monitor",
            run_id,
            "failed",
            duration_sec=round(time.time() - started_at, 2),
            error_code="ai_task_failed",
        )
        return

    monitor_candidates = build_intraday_candidates_from_results(
        parsed_results,
        datetime.now(),
    )
    risk_adjusted_candidates = apply_risk_rules(monitor_candidates, prefs)
    candidate_files = _write_candidate_outputs(
        "monitor",
        run_id,
        datetime.now(),
        risk_adjusted_candidates,
    )

    for result in parsed_results:
        alert = check_alert(result, threshold)
        if alert:
            alert = _attach_quantity_to_alert(
                alert,
                capital,
                buy_ratio,
                sell_ratio,
                positions_map,
            )
            alerts.append(alert)
            logger.info(
                f"觸發警報: {alert['stock_code']} {alert['stock_name']} "
                f"({alert['signal_type']}) - {alert['reason']} / "
                f"建議數量: {alert['suggested_quantity']}{alert['quantity_unit']}"
            )

    if alerts:
        logger.info(f"共 {len(alerts)} 檔觸發警報，寄送 email")
        email_sender = EmailSender(config["email"])
        email_sender.send_alert(alerts)
    else:
        logger.info("本次監控無觸發警報")

    _log_job_event(
        "monitor",
        run_id,
        "completed",
        duration_sec=round(time.time() - started_at, 2),
        output_files=candidate_files,
        candidate_count=len(risk_adjusted_candidates),
        alert_count=len(alerts),
    )

    logger.info("Job 3: 盤中監控完成")

