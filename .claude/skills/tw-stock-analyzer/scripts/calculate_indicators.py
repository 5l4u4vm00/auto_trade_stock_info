#!/usr/bin/env python3
"""
台灣股票技術指標計算腳本
讀取每日行情資料，結合歷史資料計算各項技術指標，並篩選出值得關注的股票
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta

def ensure_packages():
    packages = {'pandas': 'pandas', 'numpy': 'numpy', 'yfinance': 'yfinance'}
    for import_name, pip_name in packages.items():
        try:
            __import__(import_name)
        except ImportError:
            print(f"安裝 {pip_name}...")
            os.system(f"{sys.executable} -m pip install {pip_name} --break-system-packages -q")

ensure_packages()

import pandas as pd
import numpy as np

# Project root: 從 .claude/skills/tw-stock-analyzer/scripts/ 往上 4 層
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
DATA_DIR = os.path.join(PROJECT_ROOT, "tw_stock_data")


def get_historical_data(symbol, period="3mo"):
    """
    從 Yahoo Finance 取得歷史資料
    台股代號需加上 .TW（上市）或 .TWO（上櫃）
    """
    import yfinance as yf
    
    for suffix in ['.TW', '.TWO']:
        try:
            ticker = yf.Ticker(f"{symbol}{suffix}")
            hist = ticker.history(period=period)
            if len(hist) > 5:
                return hist
        except Exception:
            continue
    return None


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


def analyze_stock(symbol, daily_data_row, max_retries=2):
    """
    對單一股票進行技術分析
    結合歷史資料計算指標
    """
    result = {
        '股票代號': daily_data_row['股票代號'],
        '股票名稱': daily_data_row['股票名稱'],
        '收盤價': daily_data_row['收盤價'],
        '漲跌幅(%)': daily_data_row['漲跌幅(%)'],
        '成交量(張)': daily_data_row.get('成交量(張)', 0),
        '市場': daily_data_row.get('市場', ''),
    }
    
    # 嘗試取得歷史資料
    hist = None
    for attempt in range(max_retries):
        hist = get_historical_data(symbol)
        if hist is not None and len(hist) > 0:
            break
        time.sleep(0.5)
    
    if hist is not None and len(hist) >= 5:
        close = hist['Close']
        high = hist['High']
        low = hist['Low']
        volume = hist['Volume']
        
        # MA
        result['MA5'] = round(calculate_ma(close, 5).iloc[-1], 2)
        result['MA10'] = round(calculate_ma(close, 10).iloc[-1], 2)
        result['MA20'] = round(calculate_ma(close, 20).iloc[-1], 2)
        result['MA60'] = round(calculate_ma(close, 60).iloc[-1], 2) if len(close) >= 60 else None
        
        # RSI
        rsi = calculate_rsi(close)
        result['RSI'] = round(rsi.iloc[-1], 2)
        result['RSI_prev'] = round(rsi.iloc[-2], 2) if len(rsi) >= 2 else None
        
        # MACD
        dif, macd_signal, histogram = calculate_macd(close)
        result['MACD_DIF'] = round(dif.iloc[-1], 4)
        result['MACD_Signal'] = round(macd_signal.iloc[-1], 4)
        result['MACD_Hist'] = round(histogram.iloc[-1], 4)
        result['MACD_Hist_prev'] = round(histogram.iloc[-2], 4) if len(histogram) >= 2 else None
        
        # KD
        k, d = calculate_kd(high, low, close)
        result['K'] = round(k.iloc[-1], 2)
        result['D'] = round(d.iloc[-1], 2)
        result['K_prev'] = round(k.iloc[-2], 2) if len(k) >= 2 else None
        result['D_prev'] = round(d.iloc[-2], 2) if len(d) >= 2 else None
        
        # 布林通道
        bb_upper, bb_mid, bb_lower = calculate_bollinger(close)
        result['BB_Upper'] = round(bb_upper.iloc[-1], 2)
        result['BB_Mid'] = round(bb_mid.iloc[-1], 2)
        result['BB_Lower'] = round(bb_lower.iloc[-1], 2)
        
        # 量比
        vol_ratio = calculate_volume_ratio(volume)
        result['量比'] = round(vol_ratio.iloc[-1], 2)
        
        # === 信號判斷 ===
        signals = []
        current_price = close.iloc[-1]
        
        # RSI 信號
        if result['RSI'] < 30:
            signals.append('RSI超賣')
        elif result['RSI'] > 70:
            signals.append('RSI超買')
        if result['RSI_prev'] and result['RSI_prev'] < 30 and result['RSI'] > 30:
            signals.append('RSI超賣回升')
        
        # KD 交叉
        if result['K_prev'] and result['D_prev']:
            if result['K_prev'] <= result['D_prev'] and result['K'] > result['D']:
                signals.append('KD黃金交叉')
            elif result['K_prev'] >= result['D_prev'] and result['K'] < result['D']:
                signals.append('KD死亡交叉')
        
        if result['K'] < 20 and result['D'] < 20:
            signals.append('KD低檔')
        elif result['K'] > 80 and result['D'] > 80:
            signals.append('KD高檔')
        
        # MACD 信號
        if result['MACD_Hist_prev'] and result['MACD_Hist_prev'] < 0 and result['MACD_Hist'] > 0:
            signals.append('MACD柱翻正')
        elif result['MACD_Hist_prev'] and result['MACD_Hist_prev'] > 0 and result['MACD_Hist'] < 0:
            signals.append('MACD柱翻負')
        
        if result['MACD_DIF'] > result['MACD_Signal']:
            signals.append('DIF>MACD')
        
        # 均線信號
        if result['MA5'] > result['MA10'] and result['MA10'] > result['MA20']:
            signals.append('均線多頭排列')
        elif result['MA5'] < result['MA10'] and result['MA10'] < result['MA20']:
            signals.append('均線空頭排列')
        
        if current_price > result['MA20']:
            signals.append('站上MA20')
        elif current_price < result['MA20']:
            signals.append('跌破MA20')
        
        # 布林通道信號
        if current_price >= result['BB_Upper']:
            signals.append('觸及布林上軌')
        elif current_price <= result['BB_Lower']:
            signals.append('觸及布林下軌')
        
        bb_width = (result['BB_Upper'] - result['BB_Lower']) / result['BB_Mid'] if result['BB_Mid'] > 0 else 0
        if bb_width < 0.05:
            signals.append('布林收窄')
        
        # 量能信號
        if result['量比'] > 2.0:
            signals.append('爆量')
        elif result['量比'] > 1.5:
            signals.append('量增')
        elif result['量比'] < 0.5:
            signals.append('量縮')
        
        # 量價背離
        if result['漲跌幅(%)'] > 1 and result['量比'] < 0.7:
            signals.append('價漲量縮')
        elif result['漲跌幅(%)'] < -1 and result['量比'] > 1.5:
            signals.append('價跌量增')
        
        result['信號'] = '|'.join(signals) if signals else '無明顯信號'
        
        # 多頭/空頭分數
        bull_signals = ['RSI超賣回升', 'KD黃金交叉', 'KD低檔', 'MACD柱翻正', 'DIF>MACD',
                        '均線多頭排列', '站上MA20', '觸及布林下軌', '量增', '爆量']
        bear_signals = ['RSI超買', 'KD死亡交叉', 'KD高檔', 'MACD柱翻負',
                        '均線空頭排列', '跌破MA20', '觸及布林上軌', '價漲量縮']
        
        result['多頭分數'] = sum(1 for s in signals if s in bull_signals)
        result['空頭分數'] = sum(1 for s in signals if s in bear_signals)
        
    else:
        result['信號'] = '無歷史資料'
        result['多頭分數'] = 0
        result['空頭分數'] = 0
    
    return result


def main():
    print("=" * 60)
    print("台灣股票技術指標計算")
    print("=" * 60)
    
    # 讀取每日行情資料
    quotes_path = os.path.join(DATA_DIR, "daily_quotes.csv")
    if not os.path.exists(quotes_path):
        print(f"找不到行情資料：{quotes_path}")
        print("請先執行 fetch_twse_data.py")
        return 1
    
    df = pd.read_csv(quotes_path)
    print(f"讀取 {len(df)} 檔股票資料")
    
    # 過濾條件：只分析有一定成交量的股票
    # 成交量 > 100 張且收盤價 > 5 元
    filtered = df[(df['成交量(張)'] > 100) & (df['收盤價'] > 5)].copy()
    print(f"過濾後剩 {len(filtered)} 檔（成交量>100張 且 股價>5元）")
    
    # 進一步限制分析數量以控制 API 使用量
    # 優先分析：成交量前 200 + 漲跌幅前後各 50
    top_volume = filtered.nlargest(200, '成交量(張)')
    top_gainers = filtered.nlargest(50, '漲跌幅(%)')
    top_losers = filtered.nsmallest(50, '漲跌幅(%)')
    
    to_analyze = pd.concat([top_volume, top_gainers, top_losers]).drop_duplicates(subset='股票代號')
    print(f"將分析 {len(to_analyze)} 檔重點股票")
    
    # 逐一分析
    results = []
    total = len(to_analyze)
    
    for idx, (_, row) in enumerate(to_analyze.iterrows()):
        symbol = str(row['股票代號']).strip()
        name = str(row['股票名稱']).strip()
        
        if idx % 20 == 0:
            print(f"進度：{idx}/{total} ({idx/total*100:.0f}%)")
        
        try:
            result = analyze_stock(symbol, row)
            results.append(result)
        except Exception as e:
            print(f"  ⚠ {symbol} {name} 分析失敗：{e}")
            results.append({
                '股票代號': symbol,
                '股票名稱': name,
                '收盤價': row['收盤價'],
                '漲跌幅(%)': row['漲跌幅(%)'],
                '信號': '分析失敗',
                '多頭分數': 0,
                '空頭分數': 0,
            })
        
        # 控制 API 請求速度
        time.sleep(0.3)
    
    # 儲存指標結果
    results_df = pd.DataFrame(results)
    indicators_path = os.path.join(DATA_DIR, "indicators.csv")
    results_df.to_csv(indicators_path, index=False, encoding='utf-8-sig')
    print(f"\n指標計算結果已儲存至：{indicators_path}")
    
    # 篩選值得關注的股票
    screened = {
        'bullish': [],   # 強勢買進候選
        'watchlist': [],  # 觀察追蹤
        'bearish': [],    # 風險警示
    }
    
    for _, r in results_df.iterrows():
        entry = {
            '股票代號': r.get('股票代號', ''),
            '股票名稱': r.get('股票名稱', ''),
            '收盤價': r.get('收盤價', 0),
            '漲跌幅(%)': r.get('漲跌幅(%)', 0),
            '信號': r.get('信號', ''),
            'RSI': r.get('RSI', None),
            'K': r.get('K', None),
            'D': r.get('D', None),
            'MACD_Hist': r.get('MACD_Hist', None),
            '量比': r.get('量比', None),
            '多頭分數': r.get('多頭分數', 0),
            '空頭分數': r.get('空頭分數', 0),
        }
        
        bull = r.get('多頭分數', 0)
        bear = r.get('空頭分數', 0)
        
        if bull >= 3 and bear <= 1:
            screened['bullish'].append(entry)
        elif bull >= 1 and bear <= 1:
            screened['watchlist'].append(entry)
        elif bear >= 2:
            screened['bearish'].append(entry)
    
    # 排序
    screened['bullish'].sort(key=lambda x: x.get('多頭分數', 0), reverse=True)
    screened['watchlist'].sort(key=lambda x: x.get('多頭分數', 0), reverse=True)
    screened['bearish'].sort(key=lambda x: x.get('空頭分數', 0), reverse=True)
    
    # 限制輸出數量
    screened['bullish'] = screened['bullish'][:30]
    screened['watchlist'] = screened['watchlist'][:30]
    screened['bearish'] = screened['bearish'][:30]
    
    # 儲存篩選結果
    screened_path = os.path.join(DATA_DIR, "screened_stocks.json")
    with open(screened_path, 'w', encoding='utf-8') as f:
        json.dump(screened, f, ensure_ascii=False, indent=2)
    
    print(f"\n篩選結果已儲存至：{screened_path}")
    print(f"🟢 強勢買進候選：{len(screened['bullish'])} 檔")
    print(f"🟡 觀察追蹤清單：{len(screened['watchlist'])} 檔")
    print(f"🔴 風險警示清單：{len(screened['bearish'])} 檔")
    
    # 印出強勢股前 10
    if screened['bullish']:
        print(f"\n{'='*60}")
        print("🟢 強勢買進候選 TOP 10")
        print(f"{'='*60}")
        for i, s in enumerate(screened['bullish'][:10], 1):
            print(f"{i:2d}. {s['股票代號']} {s['股票名稱']:<8s} "
                  f"收盤:{s['收盤價']:>8.2f}  漲跌:{s['漲跌幅(%)']:>+6.2f}%  "
                  f"多頭分數:{s['多頭分數']}")
            print(f"    信號：{s['信號']}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
