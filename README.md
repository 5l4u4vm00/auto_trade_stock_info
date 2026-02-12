# auto_trade_stock

台股自動化排程分析專案。系統會定時呼叫 AI CLI 產生策略/交易計畫，並透過 Email 寄送報告與盤中警報。

## 功能概覽

- 每週新聞選股：每週固定時間產生 `strategy/news_strategy_*.md`
- 每日交易計畫：交易日上午產生 `outputs/trading_plan_*.md`
- 盤中監控警報：交易時段內定期分析推薦標的並寄送買賣提醒
- Provider 可切換：支援 `claude` 與 `custom` CLI

## 專案結構

```text
.
├── scheduler/
│   ├── main.py               # 排程主程式
│   ├── ai_runner.py          # AI CLI 呼叫與重試/逾時控制
│   ├── email_sender.py       # SMTP 寄信
│   ├── report_parser.py      # 交易計畫與個股分析結果解析
│   ├── trading_calendar.py   # 台股交易日判斷
│   ├── config.yaml           # 系統設定
│   ├── requirements.txt      # Python 套件
│   └── tests/                # 單元測試
├── strategy/                 # 新聞選股報告輸出
├── outputs/                  # 每日交易計畫輸出（執行後產生）
└── logs/                     # 排程日誌
```

## 環境需求

- Python 3.10+
- 可用的 AI CLI（預設為 `claude`）
- SMTP 帳號（預設範例為 Gmail）

## 安裝

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r scheduler/requirements.txt
mkdir -p logs outputs strategy
```

## 設定

編輯 `scheduler/config.yaml`：

1. `email`：SMTP 主機、帳號、密碼（Gmail 建議使用應用程式密碼）、收件人
2. `ai`：設定 provider、逾時、重試策略與 CLI 參數
3. `trading_preferences`：資金、風險偏好、交易週期、持股、關注產業
4. `schedule`：三個排程任務時間
5. `signal_threshold`：盤中警報觸發門檻

## 執行方式

```bash
# 啟動正式排程
python3 scheduler/main.py

# 測試 Email 設定
python3 scheduler/main.py --test-email

# 測試單一任務
python3 scheduler/main.py --test-job news
python3 scheduler/main.py --test-job daily
python3 scheduler/main.py --test-job monitor
```

## 預設排程（可於 config.yaml 修改）

- Job 1（新聞選股）：週日 `00:00`
- Job 2（每日分析）：週一到週五 `08:00`
- Job 3（盤中監控）：週一到週五 `09:00-13:30`，每 `30` 分鐘

## 輸出與日誌

- 排程日誌：`logs/scheduler.log`
- PID 檔：`scheduler/scheduler.pid`
- 新聞策略：`strategy/news_strategy_*.md`
- 交易計畫：`outputs/trading_plan_*.md`

## 測試

```bash
python3 -m unittest discover -s scheduler/tests -p "test_*.py"
```

## 注意事項

- `scheduler/trading_calendar.py` 的假日清單目前為手動維護（含 2025、2026），每年需更新。
- `daily` / `news` 任務除了 CLI 回傳成功，還要求新報告檔案實際產生才視為成功。
- 盤中監控會呼叫 `.claude/skills/single-stock-analyzer/scripts/analyze_single_stock.py`，請確保該檔案存在且可執行。
