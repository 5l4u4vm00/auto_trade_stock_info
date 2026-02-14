"""
報告解析模組
從交易計畫 markdown 擷取推薦股票，以及解析個股分析 JSON 結果
"""

import json
import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def parse_trading_plan(filepath):
    """
    從交易計畫 markdown 擷取推薦股票代號列表

    解析 generate_plan.py 產出的 trading_plan markdown 中：
    - 「買進計畫」表格中的股票代號
    - 「強勢買進候選」表格中的股票代號
    - 「觀察追蹤清單」表格中的股票代號

    Args:
        filepath: trading_plan_{date}.md 的路徑

    Returns:
        dict: {
            'buy_candidates': [stock_codes],  # 買進計畫中的股票
            'watchlist': [stock_codes],        # 觀察清單中的股票
            'all': [stock_codes],              # 所有推薦股票（去重）
        }
    """
    path = Path(filepath)
    if not path.exists():
        logger.warning(f"交易計畫不存在: {filepath}")
        return {'buy_candidates': [], 'watchlist': [], 'all': []}

    content = path.read_text(encoding='utf-8')
    buy_candidates = []
    watchlist = []

    # 解析 markdown 表格中的股票代號
    # 表格格式：| 代號 | 名稱 | ... | 或 | 標的 | 名稱 | ... |
    # 股票代號通常是 4 位數字，或 00xxx 格式（ETF）
    stock_code_pattern = re.compile(r'\b([\d]{4,6}[A-Z]?)\b')

    in_buy_section = False
    in_bullish_section = False
    in_watch_section = False

    for line in content.split('\n'):
        # 偵測章節
        if '買進計畫' in line:
            in_buy_section = True
            in_bullish_section = False
            in_watch_section = False
            continue
        elif '強勢買進候選' in line:
            in_bullish_section = True
            in_buy_section = False
            in_watch_section = False
            continue
        elif '觀察追蹤清單' in line or '觀察' in line and '清單' in line:
            in_watch_section = True
            in_buy_section = False
            in_bullish_section = False
            continue
        elif line.startswith('###') or line.startswith('---'):
            # 新章節，重置
            if not any(kw in line for kw in ['買進', '強勢', '觀察']):
                in_buy_section = False
                in_bullish_section = False
                in_watch_section = False
            continue

        # 解析表格行（以 | 開頭）
        if line.strip().startswith('|') and '---' not in line:
            # 跳過表頭
            if '代號' in line or '標的' in line or '項目' in line:
                continue

            codes = stock_code_pattern.findall(line)
            for code in codes:
                # 過濾掉明顯不是股票代號的數字（如價格、百分比）
                if _is_likely_stock_code(code, line):
                    if in_buy_section or in_bullish_section:
                        if code not in buy_candidates:
                            buy_candidates.append(code)
                    elif in_watch_section:
                        if code not in watchlist:
                            watchlist.append(code)
                    break  # 每行只取第一個匹配的股票代號

    all_stocks = list(dict.fromkeys(buy_candidates + watchlist))

    logger.info(f"解析交易計畫: 買進候選 {len(buy_candidates)} 檔, 觀察 {len(watchlist)} 檔")
    return {
        'buy_candidates': buy_candidates,
        'watchlist': watchlist,
        'all': all_stocks,
    }


def _is_likely_stock_code(code, line):
    """
    判斷一個數字字串是否可能是股票代號
    （而非價格、百分比、成交量等）
    """
    # 股票代號通常是表格中第一個欄位的數字
    parts = [p.strip() for p in line.split('|') if p.strip()]
    if not parts:
        return False

    # 檢查是否出現在第一個欄位中
    first_field = parts[0]
    if code in first_field:
        return True

    return False


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_signals(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _build_single_stock_result(data):
    bullish_signals = _normalize_signals(data.get('bullish_signals', []))
    bearish_signals = _normalize_signals(data.get('bearish_signals', []))
    suggestion = str(data.get('suggestion', '')).strip().lower()

    return {
        'stock_code': str(data.get('stock_code', '')).strip(),
        'stock_name': str(data.get('stock_name', '')).strip(),
        'price': _to_float(data.get('price', 0)),
        'suggestion': suggestion,
        'score': _to_int(data.get('score', 0)),
        'bullish_count': len(bullish_signals),
        'bearish_count': len(bearish_signals),
        'bullish_signals': bullish_signals,
        'bearish_signals': bearish_signals,
        'error': False,
    }


def _parse_single_stock_json(raw_text):
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return None

    if data.get('error'):
        logger.warning(f"個股分析回報錯誤: {data.get('message', 'unknown')}")
        return None

    return _build_single_stock_result(
        {
            'stock_code': data.get('stock_code', ''),
            'stock_name': data.get('stock_name', ''),
            'price': data.get('price', {}).get('close', 0),
            'suggestion': data.get('suggestion', ''),
            'score': data.get('score', 0),
            'bullish_signals': data.get('bullish_signals', []),
            'bearish_signals': data.get('bearish_signals', []),
        }
    )


def _parse_markdown_frontmatter(raw_text):
    stripped_text = raw_text.strip()
    if not stripped_text.startswith('---'):
        return None

    lines = stripped_text.splitlines()
    if not lines or lines[0].strip() != '---':
        return None

    end_index = -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == '---':
            end_index = idx
            break

    if end_index < 0:
        return None

    frontmatter_text = '\n'.join(lines[1:end_index])
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        logger.warning(f"frontmatter YAML 解析失敗: {exc}")
        return None

    if not isinstance(frontmatter, dict):
        return None
    return frontmatter


def _parse_single_stock_markdown(raw_text):
    frontmatter = _parse_markdown_frontmatter(raw_text)
    if not frontmatter:
        return None

    required_fields = [
        'stock_code',
        'stock_name',
        'suggestion',
        'score',
        'bullish_signals',
        'bearish_signals',
        'price_close',
    ]
    missing_fields = [field for field in required_fields if field not in frontmatter]
    if missing_fields:
        logger.warning(f"frontmatter 缺少必要欄位: {missing_fields}")
        return None

    return _build_single_stock_result(
        {
            'stock_code': frontmatter.get('stock_code', ''),
            'stock_name': frontmatter.get('stock_name', ''),
            'price': frontmatter.get('price_close', 0),
            'suggestion': frontmatter.get('suggestion', ''),
            'score': frontmatter.get('score', 0),
            'bullish_signals': frontmatter.get('bullish_signals', []),
            'bearish_signals': frontmatter.get('bearish_signals', []),
        }
    )


def parse_single_stock_result(raw_text):
    """
    解析個股分析輸出（Markdown frontmatter / JSON），判斷買賣信號

    Args:
        raw_text: 來自 AI 或腳本的輸出內容

    Returns:
        dict: {
            'stock_code': str,
            'stock_name': str,
            'price': float,
            'suggestion': str,        # buy/sell/watch/hold
            'score': int,
            'bullish_count': int,
            'bearish_count': int,
            'bullish_signals': [str],
            'bearish_signals': [str],
            'error': bool,
        }
        或 None 如果解析失敗
    """
    if not raw_text:
        return None

    # 2026-02-14 調整方式: monitor 輸出改為 Markdown + frontmatter，並保留 JSON 相容性。
    parsed_result = _parse_single_stock_markdown(raw_text)
    if parsed_result:
        return parsed_result

    parsed_result = _parse_single_stock_json(raw_text)
    if parsed_result:
        return parsed_result

    logger.error(f"個股分析結果解析失敗: {str(raw_text)[:200]}")
    return None


def check_alert(parsed_result, threshold_config):
    """
    根據解析結果和閾值設定，判斷是否需要觸發警報

    Args:
        parsed_result: parse_single_stock_result() 的回傳值
        threshold_config: dict with min_bullish_signals, min_bearish_signals

    Returns:
        dict or None: 如果觸發警報則回傳警報資訊，否則回傳 None
        {
            'stock_code': str,
            'stock_name': str,
            'signal_type': 'buy' or 'sell',
            'price': float,
            'reason': str,
        }
    """
    if not parsed_result:
        return None

    min_bull = threshold_config.get('min_bullish_signals', 3)
    min_bear = threshold_config.get('min_bearish_signals', 3)
    suggestion = parsed_result['suggestion']
    score = parsed_result['score']
    bull_count = parsed_result['bullish_count']
    bear_count = parsed_result['bearish_count']

    signal_type = None
    reason = None

    # 條件 1: suggestion 直接是 buy 或 sell
    if suggestion == 'buy':
        signal_type = 'buy'
        reason = f"建議買入 (多頭{bull_count}/空頭{bear_count}, score={score})"
    elif suggestion == 'sell':
        signal_type = 'sell'
        reason = f"建議賣出 (多頭{bull_count}/空頭{bear_count}, score={score})"
    # 條件 2: 多頭信號數 >= 閾值 且 score > 0
    elif bull_count >= min_bull and score > 0:
        signal_type = 'buy'
        signals_str = ', '.join(parsed_result['bullish_signals'][:3])
        reason = f"多頭信號 {bull_count} 個 (>={min_bull}), score={score}: {signals_str}"
    # 條件 3: 空頭信號數 >= 閾值 且 score < 0
    elif bear_count >= min_bear and score < 0:
        signal_type = 'sell'
        signals_str = ', '.join(parsed_result['bearish_signals'][:3])
        reason = f"空頭信號 {bear_count} 個 (>={min_bear}), score={score}: {signals_str}"

    if signal_type:
        return {
            'stock_code': parsed_result['stock_code'],
            'stock_name': parsed_result['stock_name'],
            'signal_type': signal_type,
            'price': parsed_result['price'],
            'reason': reason,
        }

    return None
