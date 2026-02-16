"""訊號產生引擎。"""

from datetime import date, datetime

try:
    from domain.types import CandidateSignal
except ModuleNotFoundError:  # pragma: no cover
    from scheduler.domain.types import CandidateSignal


def _clamp(value, min_value, max_value):
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def _map_action_from_suggestion(suggestion, bull_count, bear_count):
    normalized_suggestion = str(suggestion).strip().lower()
    if normalized_suggestion == "buy":
        return "buy"
    if normalized_suggestion == "sell":
        return "reduce"
    if normalized_suggestion in {"watch", "hold"}:
        return "watch"
    if bear_count > bull_count:
        return "avoid"
    return "watch"


def _build_intraday_reasons(result_item):
    reasons = []

    bullish_signals = result_item.get("bullish_signals", [])
    bearish_signals = result_item.get("bearish_signals", [])
    suggestion = str(result_item.get("suggestion", "")).strip().lower()

    if suggestion:
        reasons.append(f"suggestion={suggestion}")

    if bullish_signals:
        reasons.append(f"bullish: {', '.join(bullish_signals[:3])}")

    if bearish_signals:
        reasons.append(f"bearish: {', '.join(bearish_signals[:3])}")

    if not reasons:
        reasons.append("來源資料未提供明確訊號")

    return reasons


def build_daily_candidates_from_plan(parsed_plan, as_of_date=None):
    """由交易計畫解析結果建立每日候選訊號。"""
    # 2026-02-15 調整方式: daily 任務新增統一 CandidateSignal 輸出。
    run_date = as_of_date or date.today()
    signal_date = run_date.isoformat()
    candidates = []

    buy_candidates = parsed_plan.get("buy_candidates", []) if parsed_plan else []
    watchlist = parsed_plan.get("watchlist", []) if parsed_plan else []

    for stock_code in buy_candidates:
        candidates.append(
            CandidateSignal(
                stock_code=str(stock_code),
                signal_date=signal_date,
                technical_score=68,
                news_score=0,
                risk_penalty=0,
                total_score=68,
                action="buy",
                confidence=0.65,
                reasons=["來源: 每日交易計畫買進候選"],
                source="daily_plan",
            )
        )

    for stock_code in watchlist:
        candidates.append(
            CandidateSignal(
                stock_code=str(stock_code),
                signal_date=signal_date,
                technical_score=48,
                news_score=0,
                risk_penalty=0,
                total_score=48,
                action="watch",
                confidence=0.45,
                reasons=["來源: 每日交易計畫觀察清單"],
                source="daily_plan",
            )
        )

    return candidates


def build_intraday_candidates_from_results(parsed_results, as_of_datetime=None):
    """由盤中批次分析結果建立候選訊號。"""
    # 2026-02-15 調整方式: monitor 任務導入 deterministic 評分，降低純 LLM 依賴。
    run_datetime = as_of_datetime or datetime.now()
    signal_date = run_datetime.date().isoformat()
    candidates = []

    for result_item in parsed_results or []:
        stock_code = str(result_item.get("stock_code", "")).strip()
        if not stock_code:
            continue

        score = int(result_item.get("score", 0) or 0)
        bull_count = int(result_item.get("bullish_count", 0) or 0)
        bear_count = int(result_item.get("bearish_count", 0) or 0)

        technical_score = 50 + (score * 4) + ((bull_count - bear_count) * 3)
        technical_score = float(_clamp(technical_score, 0, 100))

        news_score = 0.0
        risk_penalty = 0.0
        if bear_count >= bull_count + 2:
            risk_penalty += 6.0
        if score < 0:
            risk_penalty += 4.0

        total_score = _clamp(technical_score + news_score - risk_penalty, 0, 100)

        confidence = 0.5 + min(abs(score), 10) * 0.03
        confidence = _clamp(confidence, 0.2, 0.95)

        action = _map_action_from_suggestion(
            result_item.get("suggestion", ""),
            bull_count,
            bear_count,
        )

        candidates.append(
            CandidateSignal(
                stock_code=stock_code,
                signal_date=signal_date,
                technical_score=technical_score,
                news_score=news_score,
                risk_penalty=risk_penalty,
                total_score=float(total_score),
                action=action,
                confidence=float(confidence),
                reasons=_build_intraday_reasons(result_item),
                source="intraday_monitor",
                metadata={
                    "score": score,
                    "bullish_count": bull_count,
                    "bearish_count": bear_count,
                    "stock_name": str(result_item.get("stock_name", "")).strip(),
                    "price": float(result_item.get("price", 0) or 0),
                },
            )
        )

    candidates.sort(key=lambda item: item.total_score, reverse=True)
    return candidates
