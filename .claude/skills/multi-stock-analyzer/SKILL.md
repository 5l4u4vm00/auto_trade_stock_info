---
name: multi-stock-analyzer
description: 多檔個股快速技術分析。當使用者一次提供多檔特定股票（例如「分析 2330 2317 2454」、「幫我同時看台積電 鴻海 聯發科」）並希望比較技術面、支撐壓力與買賣方向時觸發。若僅單一股票請改用 `single-stock-analyzer`；若是全市場掃描、選股或大盤分析請改用 `tw-stock-analyzer`。
---

# 多檔個股快速技術分析

## 概述

此技能用於一次分析多檔指定台股（最多 10 檔），輸出單一整合報告，便於橫向比較。
分析腳本會逐檔處理，若部分標的失敗會跳過並保留失敗原因，不中止整批流程。

## 與其他 Skill 的區分

| 使用者意圖                                     | 觸發 Skill                       |
| ---------------------------------------------- | -------------------------------- |
| 單一股票技術分析（例如「分析 2330」）          | `single-stock-analyzer`          |
| 多檔指定股票同時分析（例如「2330 2317 2454」） | `multi-stock-analyzer`（本技能） |
| 全市場掃描、選股、大盤交易計畫                 | `tw-stock-analyzer`              |

## 工作流程（4 階段）

### 階段一：解析多檔輸入

支援同一行輸入多檔股票，分隔符可為空白或逗號：

- `2330 2317 2454`
- `2330,2317,2454`
- `台積電 鴻海 聯發科`

規則：

- 會自動去除重複代號（保留第一次出現）
- 單次最多 10 檔，超過請提示使用者分批執行

### 階段二：執行批次分析腳本

執行：

```bash
python3 .codex/skills/multi-stock-analyzer/scripts/analyze_multi_stock.py <股票清單>
```

範例：

```bash
python3 .codex/skills/multi-stock-analyzer/scripts/analyze_multi_stock.py 2330 2317 2454
```

腳本會輸出 JSON，包含：

- `results`：成功分析清單
- `failed_symbols`：失敗清單與原因
- `analyzed_count` / `failed_count`

### 階段三：解讀與排序

收到 JSON 後：

1. 依 `score` 由高到低排序（同分再以 `change_pct` 高到低）
2. 逐檔解讀多空信號、關鍵指標、支撐壓力
3. 將成功與失敗分開呈現，避免混淆

判讀原則可參考：

```
.codex/skills/tw-stock-analyzer/references/indicator_guide.md
```

### 階段四：產出單一整合報告

先建立輸出資料夾（若不存在）：

```bash
mkdir -p intrday
```

輸出 Markdown 至：

```
intrday/multi_stock_analysis_{YYYYMMDD_HHMM}.md
```

## 報告模板

```markdown
# 多檔股票技術分析整合報告

> 分析日期：{日期時間} ｜ 成功 {analyzed_count} 檔 ｜ 失敗 {failed_count} 檔

---

## 📊 總覽比較（依多空分數排序）

| 排名 | 代號   | 名稱   | 收盤價  | 漲跌幅        | 多空分數 | 初步建議     |
| ---- | ------ | ------ | ------- | ------------- | -------- | ------------ |
| 1    | {code} | {name} | {close} | {change_pct}% | {score}  | {suggestion} |

---

## 🔍 個股明細

### {股票名稱}（{股票代號}）

- 市場：{market}
- 多頭信號：{bullish_signals}
- 空頭信號：{bearish_signals}
- 支撐：{support1}/{support2}
- 壓力：{resistance1}/{resistance2}
- 綜合判斷：{2-3 句解讀}

---

## ⚠️ 失敗清單

| 輸入    | 解析代號        | 失敗原因 |
| ------- | --------------- | -------- |
| {input} | {resolved_code} | {reason} |

---

> ⚠️ **免責聲明**：本報告僅供技術面參考，不構成投資建議。投資有風險，請審慎評估。
```

## 重要提醒

- 批次腳本重用單檔分析核心邏輯，確保判讀一致
- 若全部標的皆失敗，請清楚告知並提示檢查代號或稍後重試
- 報告數值需與 JSON 一致，不得自行推估或補值

## 依賴套件

若環境尚未安裝，請先安裝：

- `pandas`
- `numpy`
- `yfinance`
