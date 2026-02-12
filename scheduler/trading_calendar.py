"""
台股交易日判斷模組
判斷指定日期是否為台股交易日（排除週末 + 台股假日）
"""

from datetime import date, timedelta


# 台股固定假日清單（每年初需更新）
# 格式：(月, 日) 或 (月, 日, 日) 表示連續假期中的每一天
TWSE_HOLIDAYS_2025 = [
    date(2025, 1, 1),    # 元旦
    date(2025, 1, 27),   # 農曆除夕前
    date(2025, 1, 28),   # 農曆除夕
    date(2025, 1, 29),   # 春節
    date(2025, 1, 30),   # 春節
    date(2025, 1, 31),   # 春節
    date(2025, 2, 28),   # 和平紀念日
    date(2025, 4, 3),    # 兒童節（調整放假）
    date(2025, 4, 4),    # 清明節
    date(2025, 5, 1),    # 勞動節
    date(2025, 5, 30),   # 端午節（調整放假）
    date(2025, 5, 31),   # 端午節（週六補假）— 本來就不開盤
    date(2025, 10, 6),   # 中秋節
    date(2025, 10, 10),  # 國慶日
]

TWSE_HOLIDAYS_2026 = [
    date(2026, 1, 1),    # 元旦
    date(2026, 1, 2),    # 彈性放假
    date(2026, 2, 16),   # 農曆除夕前
    date(2026, 2, 17),   # 農曆除夕
    date(2026, 2, 18),   # 春節
    date(2026, 2, 19),   # 春節
    date(2026, 2, 20),   # 春節
    date(2026, 2, 27),   # 和平紀念日（調整放假）
    date(2026, 2, 28),   # 和平紀念日（週六）
    date(2026, 4, 3),    # 兒童節（調整放假）
    date(2026, 4, 4),    # 清明節（週六）
    date(2026, 4, 5),    # 清明節
    date(2026, 5, 1),    # 勞動節
    date(2026, 6, 19),   # 端午節
    date(2026, 9, 25),   # 中秋節
    date(2026, 10, 9),   # 國慶日（調整放假）
    date(2026, 10, 10),  # 國慶日（週六）
]

# 合併所有假日
ALL_HOLIDAYS = set(TWSE_HOLIDAYS_2025 + TWSE_HOLIDAYS_2026)


def is_trading_day(d=None):
    """
    判斷指定日期是否為台股交易日

    Args:
        d: date 物件，預設為今天

    Returns:
        bool: True 表示是交易日
    """
    if d is None:
        d = date.today()

    # 週六日不開盤
    if d.weekday() >= 5:
        return False

    # 台股假日不開盤
    if d in ALL_HOLIDAYS:
        return False

    return True


def next_trading_day(d=None):
    """取得下一個交易日"""
    if d is None:
        d = date.today()

    d = d + timedelta(days=1)
    while not is_trading_day(d):
        d = d + timedelta(days=1)
    return d


def prev_trading_day(d=None):
    """取得上一個交易日"""
    if d is None:
        d = date.today()

    d = d - timedelta(days=1)
    while not is_trading_day(d):
        d = d - timedelta(days=1)
    return d
