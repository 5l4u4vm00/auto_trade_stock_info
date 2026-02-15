---
name: mail-trade-recorder
description: 定期或手動讀取 Email（IMAP），篩選指定主旨關鍵字，解析信件內的股票買賣紀錄，輸出交易歷史並自動整理目前持股清單。當使用者提到「讀取信件交易訊號」、「整理買賣紀錄」、「由 email 更新持股」、「指定主旨解析買賣」等需求時使用。
---

# Mail 交易紀錄與持股整理

## 概述

此技能用於從 IMAP 信箱讀取交易信件，解析固定欄位格式的買賣紀錄，並輸出：

- `outputs/mail_trade_records.csv`：交易歷史
- `outputs/current_holdings.json`：目前持股（數量與均價）

## 執行流程

1. 執行腳本掃描未讀信件（`UNSEEN`）。
2. 以主旨「包含關鍵字」過濾目標郵件。
3. 解析 `Action / StockCode / Price / Quantity` 固定欄位。
4. 使用 `Message-ID` 做去重。
5. 寫入 CSV，重建目前持股清單 JSON。
6. 成功寫入至少一筆交易後，將該封郵件標記為已讀。

## 指令

```bash
python3 .codex/skills/mail-trade-recorder/scripts/scan_mail_trades.py \
  --subject-keyword "交易訊號"
```

可用參數：

- `--imap-host --imap-port --imap-user --imap-secret --mailbox`
- `--output-csv`（預設 `outputs/mail_trade_records.csv`）
- `--output-holdings`（預設 `outputs/current_holdings.json`）
- `--dry-run`（只驗證，不寫檔、不標記已讀）

## 交易格式

信件內文固定欄位格式如下（可多筆）：

```text
Action: BUY
StockCode: 2330
Price: 1000.5
Quantity: 2
```

## 注意事項

- 2026-02-14 調整方式：新增 mail 交易解析與持股重建 skill，採單次掃描模式。
- 成本計算採移動平均法。
- 賣超時庫存歸零，並記錄警告。
- 第一版不處理自然語句解析，只支援固定欄位。
