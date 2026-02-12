#!/usr/bin/env python3
"""
個股快速技術分析腳本
用法: python3 analyze_single_stock.py <股票代號或名稱>
輸出: JSON 格式分析結果到 stdout
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta


def ensure_packages():
    """自動安裝所需套件"""
    packages = {'pandas': 'pandas', 'numpy': 'numpy', 'yfinance': 'yfinance', 'requests': 'requests'}
    for import_name, pip_name in packages.items():
        try:
            __import__(import_name)
        except ImportError:
            os.system(f"{sys.executable} -m pip install {pip_name} --break-system-packages -q 2>/dev/null")


ensure_packages()

import pandas as pd
import numpy as np

# Project root: 從 .claude/skills/single-stock-analyzer/scripts/ 往上 4 層
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

# ============================================================
# 股票名稱 <-> 代號對照
# ============================================================

BUILTIN_NAME_MAP = {
    '台積電': '2330', '鴻海': '2317', '聯發科': '2454', '台達電': '2308', '中華電': '2412',
    '富邦金': '2881', '國泰金': '2882', '中信金': '2891', '兆豐金': '2886', '玉山金': '2884',
    '台塑': '1301', '南亞': '1303', '台化': '1326', '台塑化': '6505', '統一': '1216',
    '大立光': '3008', '日月光投控': '3711', '聯電': '2303', '南亞科': '2408', '瑞昱': '2379',
    '廣達': '2382', '仁寶': '2324', '緯創': '3231', '英業達': '2356', '和碩': '4938',
    '長榮': '2603', '陽明': '2609', '萬海': '2615', '長榮航': '2618', '華航': '2610',
    '台泥': '1101', '亞泥': '1102', '遠東新': '1402', '統一超': '2912', '全家': '5903',
    '中鋼': '2002', '正新': '2105', '裕隆': '2201', '和泰車': '2207', '光寶科': '2301',
    '華碩': '2357', '宏碁': '2353', '微星': '2377', '技嘉': '2376', '群光': '2385',
    '元大台灣50': '0050', '元大高股息': '0056', '國泰永續高股息': '00878',
    '元大美債20年': '00679B', '群創': '3481', '友達': '2409',
}

# 反向對照：代號 -> 名稱
BUILTIN_CODE_MAP = {v: k for k, v in BUILTIN_NAME_MAP.items()}


def load_name_mapping():
    """
    載入股票名稱對照表
    優先從 daily_quotes.csv 讀取，fallback 到內建對照表
    回傳 (name_to_code, code_to_name) 兩個 dict
    """
    name_to_code = dict(BUILTIN_NAME_MAP)
    code_to_name = dict(BUILTIN_CODE_MAP)

    # 嘗試讀取 daily_quotes.csv
    csv_path = os.path.join(PROJECT_ROOT, 'tw_stock_data', 'daily_quotes.csv')
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            if '股票代號' in df.columns and '股票名稱' in df.columns:
                for _, row in df.iterrows():
                    code = str(row['股票代號']).strip()
                    name = str(row['股票名稱']).strip()
                    if code and name and code != 'nan' and name != 'nan':
                        name_to_code[name] = code
                        code_to_name[code] = name
        except Exception:
            pass

    return name_to_code, code_to_name


def resolve_stock_code(user_input):
    """
    將使用者輸入轉換為 (股票代號, 股票名稱)
    支援：純代號 '2330'、中文名稱 '台積電'、混合 '2330 台積電'
    """
    user_input = user_input.strip()
    name_to_code, code_to_name = load_name_mapping()

    # 嘗試從混合格式中提取
    parts = user_input.split()

    # 情況1：純數字代號
    for part in parts:
        clean = part.strip()
        if clean and (clean.isdigit() or clean.startswith('00')):
            name = code_to_name.get(clean, '')
            return clean, name

    # 情況2：中文名稱
    for part in parts:
        clean = part.strip()
        if clean in name_to_code:
            return name_to_code[clean], clean

    # 情況3：整個輸入當作名稱查詢（模糊匹配）
    for name, code in name_to_code.items():
        if user_input in name or name in user_input:
            return code, name

    # 情況4：整個輸入當作代號
    if user_input.replace('.', '').replace('-', '').isalnum():
        return user_input, code_to_name.get(user_input, '')

    return None, None


# ============================================================
# 技術指標計算（自包含，不依賴外部模組）
# ============================================================

def calculate_ma(prices, window):
    """計算移動平均線"""
    return prices.rolling(window=window, min_periods=1).mean()


def calculate_rsi(prices, period=14):
    """計算 RSI 相對強弱指標"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calculate_macd(prices, fast=12, slow=26, signal=9):
    """計算 MACD"""
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    macd_signal = dif.ewm(span=signal, adjust=False).mean()
    histogram = dif - macd_signal
    return dif, macd_signal, histogram


def calculate_kd(high, low, close, n=9, k_smooth=3, d_smooth=3):
    """計算 KD 隨機指標"""
    lowest_low = low.rolling(window=n, min_periods=1).min()
    highest_high = high.rolling(window=n, min_periods=1).max()

    rsv = ((close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)) * 100
    rsv = rsv.fillna(50)

    k = rsv.ewm(alpha=1/k_smooth, adjust=False).mean()
    d = k.ewm(alpha=1/d_smooth, adjust=False).mean()
    return k, d


def calculate_bollinger(prices, window=20, num_std=2):
    """計算布林通道"""
    ma = prices.rolling(window=window, min_periods=1).mean()
    std = prices.rolling(window=window, min_periods=1).std()
    upper = ma + num_std * std
    lower = ma - num_std * std
    return upper, ma, lower


def calculate_volume_ratio(volumes, window=5):
    """計算量比（今日成交量 / N日平均量）"""
    avg_vol = volumes.rolling(window=window, min_periods=1).mean()
    return (volumes / avg_vol.replace(0, np.nan)).fillna(1)


# ============================================================
# 歷史資料取得
# ============================================================

def get_historical_data(symbol, period="3mo"):
    """
    從 Yahoo Finance 取得歷史資料
    先嘗試 .TW（上市），再嘗試 .TWO（上櫃）
    """
    import yfinance as yf

    market = None
    for suffix, mkt in [('.TW', '上市'), ('.TWO', '上櫃')]:
        try:
            ticker = yf.Ticker(f"{symbol}{suffix}")
            hist = ticker.history(period=period)
            if hist is not None and len(hist) > 5:
                market = mkt
                return hist, market
        except Exception:
            continue
    return None, None


# ============================================================
# 支撐壓力計算
# ============================================================

def calculate_support_resistance(hist, current_price):
    """計算支撐與壓力位"""
    close = hist['Close']
    high = hist['High']
    low = hist['Low']

    levels = []

    # MA 作為支撐壓力
    for window, label in [(5, 'MA5'), (10, 'MA10'), (20, 'MA20'), (60, 'MA60')]:
        if len(close) >= window:
            ma_val = float(calculate_ma(close, window).iloc[-1])
            levels.append({'price': ma_val, 'source': label})

    # 布林通道
    bb_upper, bb_mid, bb_lower = calculate_bollinger(close)
    levels.append({'price': float(bb_upper.iloc[-1]), 'source': '布林上軌'})
    levels.append({'price': float(bb_lower.iloc[-1]), 'source': '布林下軌'})

    # 近期高低點
    recent_high = float(high.tail(20).max())
    recent_low = float(low.tail(20).min())
    levels.append({'price': recent_high, 'source': '20日最高'})
    levels.append({'price': recent_low, 'source': '20日最低'})

    # 分為支撐和壓力
    supports = sorted(
        [l for l in levels if l['price'] < current_price],
        key=lambda x: x['price'],
        reverse=True
    )[:2]

    resistances = sorted(
        [l for l in levels if l['price'] > current_price],
        key=lambda x: x['price']
    )[:2]

    return supports, resistances


# ============================================================
# 綜合分析
# ============================================================

def analyze(symbol, name, hist, market):
    """綜合分析：計算指標 → 產生多空信號 → 支撐壓力 → 初步建議"""
    close = hist['Close']
    high = hist['High']
    low = hist['Low']
    volume = hist['Volume']

    current_price = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) >= 2 else current_price
    change_pct = round((current_price - prev_close) / prev_close * 100, 2) if prev_close else 0

    # 基本資訊
    result = {
        'stock_code': symbol,
        'stock_name': name,
        'market': market or '',
        'date': str(hist.index[-1].date()),
        'data_days': len(hist),
    }

    # 價格資料
    result['price'] = {
        'open': round(float(hist['Open'].iloc[-1]), 2),
        'high': round(float(high.iloc[-1]), 2),
        'low': round(float(low.iloc[-1]), 2),
        'close': round(current_price, 2),
        'volume': int(volume.iloc[-1]),
        'change_pct': change_pct,
    }

    # 技術指標
    indicators = {}

    # MA
    for window in [5, 10, 20, 60]:
        ma = calculate_ma(close, window)
        if len(close) >= window:
            indicators[f'MA{window}'] = round(float(ma.iloc[-1]), 2)
        else:
            indicators[f'MA{window}'] = round(float(ma.iloc[-1]), 2) if len(close) >= max(window // 2, 2) else None

    # RSI
    rsi = calculate_rsi(close)
    indicators['RSI'] = round(float(rsi.iloc[-1]), 2)
    indicators['RSI_prev'] = round(float(rsi.iloc[-2]), 2) if len(rsi) >= 2 else None

    # MACD
    dif, macd_signal, histogram = calculate_macd(close)
    indicators['MACD_DIF'] = round(float(dif.iloc[-1]), 4)
    indicators['MACD_Signal'] = round(float(macd_signal.iloc[-1]), 4)
    indicators['MACD_Hist'] = round(float(histogram.iloc[-1]), 4)
    indicators['MACD_Hist_prev'] = round(float(histogram.iloc[-2]), 4) if len(histogram) >= 2 else None

    # KD
    k, d = calculate_kd(high, low, close)
    indicators['K'] = round(float(k.iloc[-1]), 2)
    indicators['D'] = round(float(d.iloc[-1]), 2)
    indicators['K_prev'] = round(float(k.iloc[-2]), 2) if len(k) >= 2 else None
    indicators['D_prev'] = round(float(d.iloc[-2]), 2) if len(d) >= 2 else None

    # 布林通道
    bb_upper, bb_mid, bb_lower = calculate_bollinger(close)
    indicators['BB_Upper'] = round(float(bb_upper.iloc[-1]), 2)
    indicators['BB_Mid'] = round(float(bb_mid.iloc[-1]), 2)
    indicators['BB_Lower'] = round(float(bb_lower.iloc[-1]), 2)
    indicators['BB_Width'] = round((indicators['BB_Upper'] - indicators['BB_Lower']) / indicators['BB_Mid'], 4) if indicators['BB_Mid'] > 0 else 0

    # 量比
    vol_ratio = calculate_volume_ratio(volume)
    indicators['volume_ratio'] = round(float(vol_ratio.iloc[-1]), 2)

    result['indicators'] = indicators

    # ============ 多空信號判定 ============
    bullish_signals = []
    bearish_signals = []

    # RSI 信號
    if indicators['RSI'] < 30:
        bullish_signals.append('RSI 超賣（< 30）')
    elif indicators['RSI'] > 70:
        bearish_signals.append('RSI 超買（> 70）')
    if indicators['RSI_prev'] and indicators['RSI_prev'] < 30 and indicators['RSI'] > 30:
        bullish_signals.append('RSI 從超賣區回升')

    # KD 信號
    if indicators['K_prev'] is not None and indicators['D_prev'] is not None:
        if indicators['K_prev'] <= indicators['D_prev'] and indicators['K'] > indicators['D']:
            bullish_signals.append('KD 黃金交叉')
        elif indicators['K_prev'] >= indicators['D_prev'] and indicators['K'] < indicators['D']:
            bearish_signals.append('KD 死亡交叉')

    if indicators['K'] < 20 and indicators['D'] < 20:
        bullish_signals.append('KD 低檔（< 20）')
    elif indicators['K'] > 80 and indicators['D'] > 80:
        bearish_signals.append('KD 高檔（> 80）')

    # MACD 信號
    if indicators['MACD_Hist_prev'] is not None:
        if indicators['MACD_Hist_prev'] < 0 and indicators['MACD_Hist'] > 0:
            bullish_signals.append('MACD 柱狀圖翻正')
        elif indicators['MACD_Hist_prev'] > 0 and indicators['MACD_Hist'] < 0:
            bearish_signals.append('MACD 柱狀圖翻負')

    if indicators['MACD_DIF'] > indicators['MACD_Signal']:
        bullish_signals.append('DIF > Signal（多方動能）')
    else:
        bearish_signals.append('DIF < Signal（空方動能）')

    # 均線信號
    ma5 = indicators.get('MA5')
    ma10 = indicators.get('MA10')
    ma20 = indicators.get('MA20')
    ma60 = indicators.get('MA60')

    if ma5 and ma10 and ma20:
        if ma5 > ma10 > ma20:
            bullish_signals.append('均線多頭排列（MA5 > MA10 > MA20）')
        elif ma5 < ma10 < ma20:
            bearish_signals.append('均線空頭排列（MA5 < MA10 < MA20）')

    if ma20:
        if current_price > ma20:
            bullish_signals.append('股價站上 MA20')
        else:
            bearish_signals.append('股價跌破 MA20')

    if ma60:
        if current_price > ma60:
            bullish_signals.append('股價站上 MA60（季線）')
        else:
            bearish_signals.append('股價跌破 MA60（季線）')

    # 布林通道信號
    if current_price >= indicators['BB_Upper']:
        bearish_signals.append('股價觸及布林上軌')
    elif current_price <= indicators['BB_Lower']:
        bullish_signals.append('股價觸及布林下軌')

    if indicators['BB_Width'] < 0.05:
        bullish_signals.append('布林通道收窄（即將變盤）')

    # 量能信號
    vr = indicators['volume_ratio']
    if vr > 2.0:
        bullish_signals.append(f'爆量（量比 {vr}）')
    elif vr > 1.5:
        bullish_signals.append(f'量增（量比 {vr}）')
    elif vr < 0.5:
        bearish_signals.append(f'量縮（量比 {vr}）')

    # 量價背離
    if change_pct > 1 and vr < 0.7:
        bearish_signals.append('量價背離：價漲量縮')
    elif change_pct < -1 and vr > 1.5:
        bearish_signals.append('量價背離：價跌量增')

    result['bullish_signals'] = bullish_signals
    result['bearish_signals'] = bearish_signals
    result['score'] = len(bullish_signals) - len(bearish_signals)

    # ============ 支撐壓力 ============
    supports, resistances = calculate_support_resistance(hist, current_price)
    result['support'] = supports
    result['resistance'] = resistances

    # ============ 初步建議 ============
    bull_count = len(bullish_signals)
    bear_count = len(bearish_signals)

    if bull_count >= 4 and bear_count <= 2:
        suggestion = 'buy'
        trend = '多方格局明確，技術面偏多'
    elif bear_count >= 4 and bull_count <= 2:
        suggestion = 'sell'
        trend = '空方格局明確，技術面偏空'
    elif bull_count > bear_count:
        suggestion = 'watch'
        trend = '偏多但信號不夠強烈，建議觀察確認'
    elif bear_count > bull_count:
        suggestion = 'watch'
        trend = '偏空但信號不夠強烈，建議觀察確認'
    else:
        suggestion = 'hold'
        trend = '多空交織，方向不明確，建議持有觀望'

    result['suggestion'] = suggestion
    result['trend_summary'] = trend

    return result


# ============================================================
# Main
# ============================================================

def main():
    if len(sys.argv) < 2:
        error = {
            'error': True,
            'message': '請提供股票代號或名稱。用法: python3 analyze_single_stock.py <股票代號或名稱>',
            'examples': ['python3 analyze_single_stock.py 2330', 'python3 analyze_single_stock.py 台積電'],
        }
        print(json.dumps(error, ensure_ascii=False, indent=2))
        return 1

    user_input = ' '.join(sys.argv[1:])
    stock_code, stock_name = resolve_stock_code(user_input)

    if not stock_code:
        error = {
            'error': True,
            'message': f'無法辨識股票：{user_input}',
            'hint': '請輸入有效的台股代號（如 2330）或名稱（如 台積電）',
        }
        print(json.dumps(error, ensure_ascii=False, indent=2))
        return 1

    # 取得歷史資料
    hist, market = get_historical_data(stock_code)

    if hist is None or len(hist) < 5:
        error = {
            'error': True,
            'message': f'無法取得 {stock_code} {stock_name} 的歷史資料',
            'hint': '可能原因：(1) 股票代號不正確 (2) Yahoo Finance 暫時不可用 (3) 該股票已下市',
        }
        print(json.dumps(error, ensure_ascii=False, indent=2))
        return 1

    # 如果沒有名稱，嘗試從 yfinance 取得
    if not stock_name:
        stock_name = stock_code

    # 執行分析
    result = analyze(stock_code, stock_name, hist, market)
    result['error'] = False

    # 輸出 JSON
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())