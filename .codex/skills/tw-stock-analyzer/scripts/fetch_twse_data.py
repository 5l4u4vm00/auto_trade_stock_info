#!/usr/bin/env python3
"""
台灣股市資料抓取腳本
從 TWSE（上市）與 TPEX（上櫃）API 抓取股票行情資料
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta

# 自動安裝依賴
def ensure_packages():
    packages = {'pandas': 'pandas', 'requests': 'requests'}
    for import_name, pip_name in packages.items():
        try:
            __import__(import_name)
        except ImportError:
            print(f"安裝 {pip_name}...")
            os.system(f"{sys.executable} -m pip install {pip_name} --break-system-packages -q")

ensure_packages()

import pandas as pd
import requests

# Project root: 從 .claude/skills/tw-stock-analyzer/scripts/ 往上 4 層
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "tw_stock_data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}


def get_latest_trading_date():
    """取得最近的交易日（排除週末）"""
    today = datetime.now()
    # 台灣時間 UTC+8
    tw_now = today + timedelta(hours=8) if today.utcoffset() is None else today
    
    d = tw_now.date()
    # 若是週末，往前推到週五
    while d.weekday() >= 5:  # 5=Saturday, 6=Sunday
        d -= timedelta(days=1)
    return d


def fetch_twse_daily(date=None):
    """
    從 TWSE 抓取上市股票每日收盤行情
    API: https://www.twse.com.tw/exchangeReport/MI_INDEX
    """
    if date is None:
        date = get_latest_trading_date()
    
    date_str = date.strftime('%Y%m%d')
    url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={date_str}&type=ALLBUT0999"
    
    print(f"正在抓取 TWSE 上市股票資料（{date_str}）...")
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get('stat') != 'OK':
            print(f"TWSE API 回傳狀態：{data.get('stat', 'unknown')}")
            # 可能是假日，往前嘗試
            if date.weekday() < 5:
                prev_date = date - timedelta(days=1)
                while prev_date.weekday() >= 5:
                    prev_date -= timedelta(days=1)
                print(f"嘗試取得前一交易日（{prev_date}）資料...")
                return fetch_twse_daily(prev_date)
            return None, date_str
        
        # 解析資料 - tables[8] 通常是個股行情
        records = []
        for table in data.get('tables', []):
            title = table.get('title', '')
            if '個股' in title or '每日收盤行情' in title:
                fields = table.get('fields', [])
                for row in table.get('data', []):
                    if len(row) >= 10:
                        try:
                            record = {
                                '股票代號': row[0].strip(),
                                '股票名稱': row[1].strip(),
                                '成交股數': _parse_number(row[2]),
                                '成交筆數': _parse_number(row[3]),
                                '成交金額': _parse_number(row[4]),
                                '開盤價': _parse_price(row[5]),
                                '最高價': _parse_price(row[6]),
                                '最低價': _parse_price(row[7]),
                                '收盤價': _parse_price(row[8]),
                                '漲跌': row[9].strip() if len(row) > 9 else '',
                                '漲跌價差': _parse_price(row[10]) if len(row) > 10 else 0,
                            }
                            records.append(record)
                        except (ValueError, IndexError):
                            continue
        
        if records:
            df = pd.DataFrame(records)
            # 過濾掉無效資料
            df = df[df['收盤價'] > 0].copy()
            # 計算漲跌幅
            df['漲跌幅(%)'] = df.apply(
                lambda r: round((r['漲跌價差'] / (r['收盤價'] - r['漲跌價差'])) * 100, 2) 
                if r['收盤價'] - r['漲跌價差'] > 0 else 0, axis=1
            )
            df['成交量(張)'] = (df['成交股數'] / 1000).astype(int)
            df['市場'] = '上市'
            print(f"成功取得 {len(df)} 檔上市股票資料")
            return df, date_str
        else:
            print("未能解析出個股資料，嘗試備用格式...")
            # 嘗試 data9 格式（舊版 API）
            if 'data9' in data:
                return _parse_data9(data['data9'], date_str)
            return None, date_str
            
    except requests.exceptions.RequestException as e:
        print(f"TWSE API 請求失敗：{e}")
        return None, date_str


def _parse_data9(data9, date_str):
    """解析舊版 TWSE API data9 格式"""
    records = []
    for row in data9:
        try:
            records.append({
                '股票代號': row[0].strip(),
                '股票名稱': row[1].strip(),
                '成交股數': _parse_number(row[2]),
                '成交筆數': _parse_number(row[3]),
                '成交金額': _parse_number(row[4]),
                '開盤價': _parse_price(row[5]),
                '最高價': _parse_price(row[6]),
                '最低價': _parse_price(row[7]),
                '收盤價': _parse_price(row[8]),
                '漲跌': row[9].strip(),
                '漲跌價差': _parse_price(row[10]),
            })
        except (ValueError, IndexError):
            continue
    
    if records:
        df = pd.DataFrame(records)
        df = df[df['收盤價'] > 0].copy()
        df['漲跌幅(%)'] = df.apply(
            lambda r: round((r['漲跌價差'] / (r['收盤價'] - r['漲跌價差'])) * 100, 2) 
            if r['收盤價'] - r['漲跌價差'] > 0 else 0, axis=1
        )
        df['成交量(張)'] = (df['成交股數'] / 1000).astype(int)
        df['市場'] = '上市'
        print(f"(data9) 成功取得 {len(df)} 檔上市股票資料")
        return df, date_str
    return None, date_str


def fetch_tpex_daily(date=None):
    """
    從 TPEX 抓取上櫃股票每日收盤行情
    """
    if date is None:
        date = get_latest_trading_date()
    
    # TPEX 用民國年
    roc_year = date.year - 1911
    date_str_roc = f"{roc_year}/{date.month:02d}/{date.day:02d}"
    date_str = date.strftime('%Y%m%d')
    
    url = f"https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?l=zh-tw&d={date_str_roc}&se=EW"
    
    print(f"正在抓取 TPEX 上櫃股票資料（{date_str}）...")
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        records = []
        for row in data.get('aaData', []):
            try:
                records.append({
                    '股票代號': str(row[0]).strip(),
                    '股票名稱': str(row[1]).strip(),
                    '收盤價': _parse_price(row[2]),
                    '漲跌價差': _parse_price(row[3]),
                    '開盤價': _parse_price(row[4]),
                    '最高價': _parse_price(row[5]),
                    '最低價': _parse_price(row[6]),
                    '成交股數': _parse_number(row[7]),
                    '成交金額': _parse_number(row[8]),
                    '成交筆數': _parse_number(row[9]),
                })
            except (ValueError, IndexError):
                continue
        
        if records:
            df = pd.DataFrame(records)
            df = df[df['收盤價'] > 0].copy()
            df['漲跌幅(%)'] = df.apply(
                lambda r: round((r['漲跌價差'] / (r['收盤價'] - r['漲跌價差'])) * 100, 2) 
                if r['收盤價'] - r['漲跌價差'] > 0 else 0, axis=1
            )
            df['成交量(張)'] = (df['成交股數'] / 1000).astype(int)
            df['市場'] = '上櫃'
            print(f"成功取得 {len(df)} 檔上櫃股票資料")
            return df, date_str
        
        print("TPEX 未回傳資料（可能為假日）")
        return None, date_str
        
    except requests.exceptions.RequestException as e:
        print(f"TPEX API 請求失敗：{e}")
        return None, date_str


def fetch_twse_index(date=None):
    """抓取大盤指數資料"""
    if date is None:
        date = get_latest_trading_date()
    
    date_str = date.strftime('%Y%m%d')
    url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={date_str}&type=IND"
    
    print("正在抓取大盤指數...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        data = resp.json()
        
        index_info = {}
        if data.get('stat') == 'OK':
            for table in data.get('tables', []):
                for row in table.get('data', []):
                    if len(row) >= 2:
                        name = str(row[0]).strip()
                        if '發行量加權' in name or '加權' in name:
                            index_info['加權指數'] = row[1] if len(row) > 1 else ''
                            index_info['漲跌'] = row[2] if len(row) > 2 else ''
        
        return index_info
    except Exception as e:
        print(f"大盤指數抓取失敗：{e}")
        return {}


def _parse_number(s):
    """解析數字字串（移除逗號）"""
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().replace(',', '').replace('--', '0').replace('---', '0')
    try:
        return float(s)
    except ValueError:
        return 0


def _parse_price(s):
    """解析價格字串"""
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().replace(',', '').replace('--', '0').replace('---', '0').replace(' ', '')
    if s in ('', 'X', 'x', '--', '---', '除息', '除權', '除權息'):
        return 0
    try:
        return float(s)
    except ValueError:
        return 0


def main():
    print("=" * 60)
    print("台灣股市每日資料抓取")
    print("=" * 60)
    
    date = get_latest_trading_date()
    print(f"目標日期：{date}")
    
    # 抓取上市股票
    twse_df, twse_date = fetch_twse_daily(date)
    time.sleep(3)  # 避免請求過快
    
    # 抓取上櫃股票
    tpex_df, tpex_date = fetch_tpex_daily(date)
    time.sleep(1)
    
    # 抓取大盤指數
    index_info = fetch_twse_index(date)
    
    # 合併資料
    dfs = []
    if twse_df is not None:
        dfs.append(twse_df)
    if tpex_df is not None:
        dfs.append(tpex_df)
    
    if dfs:
        combined = pd.concat(dfs, ignore_index=True)
        
        # 儲存完整資料
        output_path = os.path.join(OUTPUT_DIR, "daily_quotes.csv")
        combined.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"\n完整行情資料已儲存至：{output_path}")
        print(f"共 {len(combined)} 檔股票")
        
        # 儲存摘要統計
        summary = {
            'date': str(date),
            'twse_count': len(twse_df) if twse_df is not None else 0,
            'tpex_count': len(tpex_df) if tpex_df is not None else 0,
            'total_count': len(combined),
            'index_info': index_info,
            'top_gainers': combined.nlargest(20, '漲跌幅(%)')[
                ['股票代號', '股票名稱', '收盤價', '漲跌幅(%)', '成交量(張)', '市場']
            ].to_dict('records'),
            'top_losers': combined.nsmallest(20, '漲跌幅(%)')[
                ['股票代號', '股票名稱', '收盤價', '漲跌幅(%)', '成交量(張)', '市場']
            ].to_dict('records'),
            'top_volume': combined.nlargest(20, '成交量(張)')[
                ['股票代號', '股票名稱', '收盤價', '漲跌幅(%)', '成交量(張)', '市場']
            ].to_dict('records'),
        }
        
        # 市場統計
        up_count = len(combined[combined['漲跌幅(%)'] > 0])
        down_count = len(combined[combined['漲跌幅(%)'] < 0])
        flat_count = len(combined[combined['漲跌幅(%)'] == 0])
        summary['market_breadth'] = {
            'up': up_count,
            'down': down_count,
            'flat': flat_count,
            'up_ratio': round(up_count / len(combined) * 100, 1) if len(combined) > 0 else 0,
        }
        
        summary_path = os.path.join(OUTPUT_DIR, "daily_summary.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"摘要統計已儲存至：{summary_path}")
        
        # 輸出快速概覽
        print(f"\n{'=' * 60}")
        print(f"市場概覽 - {date}")
        print(f"{'=' * 60}")
        if index_info:
            print(f"加權指數：{index_info.get('加權指數', 'N/A')}  漲跌：{index_info.get('漲跌', 'N/A')}")
        mb = summary['market_breadth']
        print(f"上漲：{mb['up']} 家 | 下跌：{mb['down']} 家 | 平盤：{mb['flat']} 家")
        print(f"漲跌比：{mb['up_ratio']}%")
        
    else:
        print("\n⚠️ 未能取得任何股票資料")
        print("可能原因：今日非交易日、API 暫時無法連線")
        
        # 寫入空的 summary 檔
        summary = {'date': str(date), 'error': '無法取得資料', 'total_count': 0}
        summary_path = os.path.join(OUTPUT_DIR, "daily_summary.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    
    return 0 if dfs else 1


if __name__ == '__main__':
    sys.exit(main())
