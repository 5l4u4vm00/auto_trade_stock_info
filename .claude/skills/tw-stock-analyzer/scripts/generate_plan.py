#!/usr/bin/env python3
"""
交易計畫產生腳本
根據篩選結果與使用者偏好，產出完整的每日交易計畫 Markdown 文件
"""

import os
import sys
import json
from datetime import datetime

# Project root: 從 .claude/skills/tw-stock-analyzer/scripts/ 往上 4 層
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
DATA_DIR = os.path.join(PROJECT_ROOT, "tw_stock_data")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")


def load_data():
    """載入分析資料"""
    data = {}
    
    # 每日摘要
    summary_path = os.path.join(DATA_DIR, "daily_summary.json")
    if os.path.exists(summary_path):
        with open(summary_path, 'r', encoding='utf-8') as f:
            data['summary'] = json.load(f)
    
    # 篩選結果
    screened_path = os.path.join(DATA_DIR, "screened_stocks.json")
    if os.path.exists(screened_path):
        with open(screened_path, 'r', encoding='utf-8') as f:
            data['screened'] = json.load(f)
    
    return data


def generate_plan(data, preferences=None):
    """
    產生交易計畫
    
    preferences: dict with keys:
        - risk_level: 'aggressive' | 'moderate' | 'conservative'
        - capital: float (可用資金，萬元)
        - period: 'day_trade' | 'short' | 'swing'
        - focus_sectors: list of str
        - focus_stocks: list of str
        - current_holdings: list of str
    """
    if preferences is None:
        preferences = {
            'risk_level': 'moderate',
            'capital': 100,
            'period': 'short',
            'focus_sectors': [],
            'focus_stocks': [],
            'current_holdings': [],
        }
    
    summary = data.get('summary', {})
    screened = data.get('screened', {})
    date_str = summary.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    # 根據風險偏好調整參數
    risk_config = {
        'aggressive': {
            'max_single_pct': 30,
            'max_total_pct': 90,
            'stop_loss_pct': 5,
            'min_bull_score': 2,
            'label': '積極型',
        },
        'moderate': {
            'max_single_pct': 20,
            'max_total_pct': 70,
            'stop_loss_pct': 3,
            'min_bull_score': 3,
            'label': '穩健型',
        },
        'conservative': {
            'max_single_pct': 15,
            'max_total_pct': 50,
            'stop_loss_pct': 2,
            'min_bull_score': 4,
            'label': '保守型',
        },
    }
    
    risk = risk_config.get(preferences.get('risk_level', 'moderate'), risk_config['moderate'])
    capital = preferences.get('capital', 100)
    
    # 組裝 Markdown
    lines = []
    lines.append(f"# 📊 台股每日交易計畫")
    lines.append(f"## 日期：{date_str}")
    lines.append(f"")
    lines.append(f"> 風險策略：**{risk['label']}** ｜ 可用資金：**{capital} 萬元** ｜ "
                 f"交易週期：**{_period_label(preferences.get('period', 'short'))}**")
    lines.append(f"")
    
    # 一、市場概況
    lines.append("---")
    lines.append("### 一、市場概況")
    lines.append("")
    
    idx_info = summary.get('index_info', {})
    mb = summary.get('market_breadth', {})
    
    lines.append(f"| 項目 | 數值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 加權指數 | {idx_info.get('加權指數', 'N/A')} |")
    lines.append(f"| 漲跌 | {idx_info.get('漲跌', 'N/A')} |")
    lines.append(f"| 上漲家數 | {mb.get('up', 'N/A')} |")
    lines.append(f"| 下跌家數 | {mb.get('down', 'N/A')} |")
    lines.append(f"| 平盤家數 | {mb.get('flat', 'N/A')} |")
    lines.append(f"| 漲跌比 | {mb.get('up_ratio', 'N/A')}% |")
    lines.append("")
    
    # 漲幅排行
    if summary.get('top_gainers'):
        lines.append("**漲幅前 10：**")
        lines.append("")
        lines.append("| 代號 | 名稱 | 收盤價 | 漲跌幅 | 成交量(張) |")
        lines.append("|------|------|--------|--------|------------|")
        for s in summary['top_gainers'][:10]:
            lines.append(f"| {s['股票代號']} | {s['股票名稱']} | {s['收盤價']:.2f} | "
                        f"+{s['漲跌幅(%)']:.2f}% | {s['成交量(張)']:,} |")
        lines.append("")
    
    # 跌幅排行
    if summary.get('top_losers'):
        lines.append("**跌幅前 10：**")
        lines.append("")
        lines.append("| 代號 | 名稱 | 收盤價 | 漲跌幅 | 成交量(張) |")
        lines.append("|------|------|--------|--------|------------|")
        for s in summary['top_losers'][:10]:
            lines.append(f"| {s['股票代號']} | {s['股票名稱']} | {s['收盤價']:.2f} | "
                        f"{s['漲跌幅(%)']:.2f}% | {s['成交量(張)']:,} |")
        lines.append("")
    
    # 二、技術面篩選結果
    lines.append("---")
    lines.append("### 二、技術面篩選結果")
    lines.append("")
    
    # 強勢候選
    bullish = screened.get('bullish', [])
    if bullish:
        lines.append(f"#### 🟢 強勢買進候選（{len(bullish)} 檔）")
        lines.append("")
        lines.append("| 代號 | 名稱 | 收盤價 | 漲跌幅 | RSI | K/D | 量比 | 多頭分數 | 關鍵信號 |")
        lines.append("|------|------|--------|--------|-----|-----|------|----------|----------|")
        for s in bullish[:15]:
            rsi = f"{s['RSI']:.0f}" if s.get('RSI') else '-'
            kd = f"{s['K']:.0f}/{s['D']:.0f}" if s.get('K') else '-'
            vr = f"{s['量比']:.1f}" if s.get('量比') else '-'
            signals = s.get('信號', '').replace('|', ', ')
            lines.append(f"| {s['股票代號']} | {s['股票名稱']} | {s['收盤價']:.2f} | "
                        f"{s['漲跌幅(%)']:+.2f}% | {rsi} | {kd} | {vr} | "
                        f"{s.get('多頭分數', 0)} | {signals} |")
        lines.append("")
    
    # 觀察清單
    watchlist = screened.get('watchlist', [])
    if watchlist:
        lines.append(f"#### 🟡 觀察追蹤清單（{len(watchlist)} 檔，顯示前 10）")
        lines.append("")
        lines.append("| 代號 | 名稱 | 收盤價 | 漲跌幅 | 關鍵信號 |")
        lines.append("|------|------|--------|--------|----------|")
        for s in watchlist[:10]:
            signals = s.get('信號', '').replace('|', ', ')
            lines.append(f"| {s['股票代號']} | {s['股票名稱']} | {s['收盤價']:.2f} | "
                        f"{s['漲跌幅(%)']:+.2f}% | {signals} |")
        lines.append("")
    
    # 風險警示
    bearish = screened.get('bearish', [])
    if bearish:
        lines.append(f"#### 🔴 風險警示清單（{len(bearish)} 檔，顯示前 10）")
        lines.append("")
        lines.append("| 代號 | 名稱 | 收盤價 | 漲跌幅 | 空頭分數 | 警示信號 |")
        lines.append("|------|------|--------|--------|----------|----------|")
        for s in bearish[:10]:
            signals = s.get('信號', '').replace('|', ', ')
            lines.append(f"| {s['股票代號']} | {s['股票名稱']} | {s['收盤價']:.2f} | "
                        f"{s['漲跌幅(%)']:+.2f}% | {s.get('空頭分數', 0)} | {signals} |")
        lines.append("")
    
    # 三、交易策略
    lines.append("---")
    lines.append("### 三、交易策略")
    lines.append("")
    
    # 買進計畫
    buy_candidates = [s for s in bullish if s.get('多頭分數', 0) >= risk['min_bull_score']]
    
    if buy_candidates:
        max_per_stock = capital * risk['max_single_pct'] / 100
        
        lines.append("#### 📈 買進計畫")
        lines.append("")
        lines.append("| 標的 | 名稱 | 建議進場價 | 停損價 | 預計部位(萬) | 理由 |")
        lines.append("|------|------|------------|--------|--------------|------|")
        
        for s in buy_candidates[:5]:
            price = s['收盤價']
            stop_loss = round(price * (1 - risk['stop_loss_pct'] / 100), 2)
            position = min(max_per_stock, round(capital * 0.15, 1))
            signals = s.get('信號', '').replace('|', ', ')[:40]
            lines.append(f"| {s['股票代號']} | {s['股票名稱']} | {price:.2f} | "
                        f"{stop_loss:.2f} | {position:.1f} | {signals} |")
        lines.append("")
    else:
        lines.append("今日無符合條件的買進標的。")
        lines.append("")
    
    # 持股檢視
    holdings = preferences.get('current_holdings', [])
    if holdings:
        lines.append("#### 📋 持股檢視")
        lines.append("")
        
        # 檢查持股是否出現在風險清單中
        bearish_codes = [s['股票代號'] for s in bearish]
        for h in holdings:
            if h in bearish_codes:
                stock = next((s for s in bearish if s['股票代號'] == h), None)
                if stock:
                    lines.append(f"- ⚠️ **{h} {stock['股票名稱']}**：出現空頭信號（{stock.get('信號', '')}），建議減碼或設定停損")
            else:
                lines.append(f"- ✅ **{h}**：未出現明顯風險信號，可繼續持有")
        lines.append("")
    
    # 四、風險管理
    lines.append("---")
    lines.append("### 四、風險管理")
    lines.append("")
    lines.append(f"| 項目 | 設定 |")
    lines.append(f"|------|------|")
    lines.append(f"| 風險類型 | {risk['label']} |")
    lines.append(f"| 單一標的最大部位 | 總資金 {risk['max_single_pct']}%（{capital * risk['max_single_pct'] / 100:.1f} 萬元） |")
    lines.append(f"| 今日總曝險上限 | 總資金 {risk['max_total_pct']}%（{capital * risk['max_total_pct'] / 100:.1f} 萬元） |")
    lines.append(f"| 停損幅度 | {risk['stop_loss_pct']}% |")
    lines.append(f"| 停損紀律 | 跌破停損價立即出場，不猶豫 |")
    lines.append("")
    
    # 五、備註
    lines.append("---")
    lines.append("### 五、備註與提醒")
    lines.append("")
    lines.append("- 盤前留意國際股市走勢（美股、日股）與台指期貨方向")
    lines.append("- 關注當日重要財經事件與法說會")
    lines.append("- 嚴守停損紀律，保護本金")
    lines.append("- 避免在開盤前 15 分鐘追價")
    lines.append("")
    
    # 免責聲明
    lines.append("---")
    lines.append("")
    lines.append("### ⚠️ 免責聲明")
    lines.append("")
    lines.append("本計畫由技術指標自動分析產生，**僅供參考，不構成投資建議**。")
    lines.append("投資有風險，過去的表現不代表未來的結果。請審慎評估自身風險承受能力，")
    lines.append("並在做出任何投資決定前諮詢合格的財務顧問。")
    lines.append("")
    lines.append(f"*產生時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    
    return '\n'.join(lines)


def _period_label(period):
    labels = {
        'day_trade': '當沖',
        'short': '短線（數日）',
        'swing': '波段（數週）',
    }
    return labels.get(period, period)


def main():
    """CLI 入口"""
    data = load_data()
    
    if not data:
        print("找不到分析資料，請先執行資料抓取與指標計算腳本")
        return 1
    
    # 預設偏好（實際使用時由 Claude 根據使用者回饋傳入）
    preferences = {}
    
    # 從命令列參數讀取偏好 JSON
    if len(sys.argv) > 1:
        try:
            preferences = json.loads(sys.argv[1])
        except json.JSONDecodeError:
            print("偏好設定 JSON 格式錯誤，使用預設值")
    
    plan_md = generate_plan(data, preferences)
    
    # 儲存計畫
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    date_str = data.get('summary', {}).get('date', datetime.now().strftime('%Y-%m-%d'))
    filename = f"trading_plan_{date_str.replace('-', '')}.md"
    output_path = os.path.join(OUTPUT_DIR, filename)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(plan_md)
    
    print(f"交易計畫已儲存至：{output_path}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
