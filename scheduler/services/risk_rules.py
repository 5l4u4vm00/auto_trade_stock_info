"""風險規則處理。"""

try:
    from domain.types import CandidateSignal
except ModuleNotFoundError:  # pragma: no cover
    from scheduler.domain.types import CandidateSignal


DEFAULT_MAX_BUY_SIGNALS = 5
DEFAULT_MIN_BUY_CONFIDENCE = 0.55


def _clone_candidate(candidate):
    return CandidateSignal(**candidate.to_dict())


def apply_risk_rules(candidates, preferences=None):
    """套用基礎風險限制，回傳調整後候選訊號。"""
    # 2026-02-15 調整方式: 新增 buy 訊號數量與信心門檻風險控制。
    if not candidates:
        return []

    prefs = preferences if isinstance(preferences, dict) else {}
    capital = float(prefs.get("capital", 0) or 0)
    max_buy_signals = int(prefs.get("max_buy_signals", DEFAULT_MAX_BUY_SIGNALS) or 0)
    min_buy_confidence = float(
        prefs.get("min_buy_confidence", DEFAULT_MIN_BUY_CONFIDENCE) or 0
    )

    max_buy_signals = max(0, max_buy_signals)
    min_buy_confidence = max(0, min(1, min_buy_confidence))

    sorted_candidates = sorted(
        [_clone_candidate(item) for item in candidates],
        key=lambda item: item.total_score,
        reverse=True,
    )

    buy_count = 0
    for candidate in sorted_candidates:
        if candidate.action != "buy":
            continue

        if capital <= 0:
            candidate.action = "watch"
            candidate.risk_penalty += 10
            candidate.total_score = max(0, candidate.total_score - 10)
            candidate.reasons.append("風險規則: 可用資金 <= 0，降為 watch")
            continue

        if candidate.confidence < min_buy_confidence:
            candidate.action = "watch"
            candidate.risk_penalty += 5
            candidate.total_score = max(0, candidate.total_score - 5)
            candidate.reasons.append(
                "風險規則: 信心低於 min_buy_confidence，降為 watch"
            )
            continue

        if buy_count >= max_buy_signals:
            candidate.action = "watch"
            candidate.risk_penalty += 4
            candidate.total_score = max(0, candidate.total_score - 4)
            candidate.reasons.append("風險規則: 超過每日 buy 訊號上限，降為 watch")
            continue

        buy_count += 1

    sorted_candidates.sort(key=lambda item: item.total_score, reverse=True)
    return sorted_candidates
