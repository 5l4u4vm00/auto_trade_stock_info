# auto_trade_stock_info

台股自動化排程分析專案。系統透過 APScheduler 定時觸發 AI 任務，產生策略報告與盤中警報，並透過 Email 寄送結果。

## 功能概覽

- 每週新聞選股：產生 `strategy/news_strategy_*.md`
- 每日交易計畫：產生 `outputs/trading_plan_*.md`
- 盤中監控警報：批次分析推薦標的，符合條件即寄送買賣提醒
- 候選訊號輸出：每日與盤中任務都會輸出 JSON/Markdown 候選清單
- Mail 交易解析：手動解析 Email 交易訊號，更新交易歷史與目前持股

## 系統流程（高層）

1. `scheduler/main.py` 載入設定、註冊排程、維護 PID。
2. `scheduler/app/scheduler_setup.py` 註冊 `news`、`daily`、`monitor` 三個任務。
3. 各任務透過 `scheduler/ai_runner.py` 呼叫 AI CLI（`claude` 或 `codex`）。
4. 任務驗證報告檔案是否產生，再做解析、風險規則、寄信。
5. 輸出報告、候選訊號、日誌，供後續追蹤與維運。

## 專案結構

```text
.
├── scheduler/
│   ├── main.py
│   ├── config.yaml
│   ├── requirements.txt
│   ├── ai_runner.py
│   ├── email_sender.py
│   ├── report_parser.py
│   ├── trading_calendar.py
│   ├── app/
│   │   ├── config_runtime.py
│   │   ├── pid_guard.py
│   │   └── scheduler_setup.py
│   ├── jobs/
│   │   ├── news_job.py
│   │   ├── daily_job.py
│   │   ├── monitor_job.py
│   │   └── common.py
│   ├── services/
│   │   ├── signal_engine.py
│   │   └── risk_rules.py
│   ├── reporting/
│   │   └── report_writer.py
│   └── tests/
├── strategy/        # 週報輸出（執行後產生）
├── outputs/         # 日報、候選訊號、持股（執行後產生）
├── intraday/        # 盤中個股分析輸出（執行後產生）
├── logs/            # 排程日誌
├── Dockerfile
└── docker-compose.yaml
```

## 環境需求

- Python `3.10+`（目前 Docker 映像使用 `3.11`）
- 可用的 AI CLI
  - `claude` 或 `codex`
- SMTP 帳號（範例為 Gmail SMTP）
- 可選：Docker / Docker Compose

## 快速開始（本機）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r scheduler/requirements.txt
mkdir -p logs outputs strategy intraday
```

## 設定說明

### 1) 環境變數

`scheduler/config.yaml` 支援 `${ENV}` 與 `${ENV:default}` 語法。建議先複製 `.env.example`：

```bash
cp .env.example .env
```

填入 SMTP 參數後，載入環境變數：

```bash
set -a
source .env
set +a
```

主要變數：

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_SENDER`
- `SMTP_AUTH_SECRET`
- `SMTP_RECIPIENT`
- `TZ`

### 2) `scheduler/config.yaml`

重點區塊：

- `email`：SMTP 設定
- `ai`：provider、timeout、retry、provider-specific 設定
- `ai.skill_enforcement`：任務對應 skill 驗證與同步策略
- `trading_preferences`：資金、風險、持股、關注產業
- `schedule`：三個排程任務時間
- `signal_threshold`：盤中警報門檻

目前預設 task skill 對應：

```yaml
ai:
  skill_enforcement:
    task_skill_map:
      news: "news-stock-picker"
      daily: "tw-stock-analyzer"
      monitor: "multi-stock-analyzer"
      monitor_single: "single-stock-analyzer"
```

### 3) 預設排程

- 新聞選股：`sun 00:00`
- 每日分析：`mon-fri 08:00`
- 盤中監控：`mon-fri 09:00-13:30`，每 `10` 分鐘

### 4) 任務成功判定規則

- `news`：AI CLI 成功且有新 `strategy/news_strategy_*.md`
- `daily`：AI CLI 成功且有新 `outputs/trading_plan_*.md`
- `monitor`：AI CLI 成功且有新 `intraday/stock_analysis_*.md`

## 實作流程（SOP + 指令）

### 步驟 A：初始化環境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r scheduler/requirements.txt
mkdir -p logs outputs strategy intraday
```

### 步驟 B：設定機敏參數

1. 編輯 `.env`（至少填 SMTP 欄位）。
2. 載入到 shell：

```bash
set -a
source .env
set +a
```

3. 檢查 `scheduler/config.yaml` 的 provider 與排程時間。

### 步驟 C：驗證 Email

```bash
python3 scheduler/main.py --test-email
```

預期：終端顯示 Email 測試成功，且收件匣收到測試信。

### 步驟 D：驗證單一任務

```bash
python3 scheduler/main.py --test-job news
python3 scheduler/main.py --test-job daily
python3 scheduler/main.py --test-job monitor
```

驗證重點：

- `news`：產生 `strategy/news_strategy_*.md`
- `daily`：產生 `outputs/trading_plan_*.md`
- `monitor`：需同時滿足「交易日 + 監控時段 + 有交易計畫」，才會實際監控

### 步驟 E：啟動正式排程

```bash
python3 scheduler/main.py
```

預設行為：

- 建立 PID：`scheduler/scheduler.pid`
- 日誌寫入：`logs/scheduler.log`
- 註冊三個排程任務

### 步驟 F：檢查輸出與日誌

```bash
tail -f logs/scheduler.log
```

觀察 `job_event=` JSON 日誌，確認每個任務有 `start`、`completed` 或合理的 `skipped` 原因。

### 步驟 G：日常維運檢核

1. 每日確認 `outputs/trading_plan_*.md` 是否持續更新。
2. 每日確認 `outputs/candidates/*.json`、`outputs/candidates/*.md` 是否產生。
3. 每年更新 `scheduler/trading_calendar.py` 假日清單。
4. 若排程異常中斷，確認並清理殘留 `scheduler/scheduler.pid`。

## Docker 流程（可選）

> 目前 `docker-compose.yaml` 主要提供執行環境與 volume，不會自動啟動 `scheduler/main.py`。

### 1) 建立與啟動容器

```bash
docker compose up -d --build
```

### 2) 進入容器

```bash
docker compose exec scheduler bash
```

若無 `bash` 可改用 `sh`：

```bash
docker compose exec scheduler sh
```

### 3) 在容器內啟動排程

```bash
python3 scheduler/main.py
```

### 4) Volume 對應

- `scheduler_logs` -> `/app/logs`
- `scheduler_outputs` -> `/app/outputs`
- `scheduler_strategy` -> `/app/strategy`
- `scheduler_intraday` -> `/app/intraday`

## 手動流程：Mail 交易解析

```bash
python3 .codex/skills/mail-trade-recorder/scripts/scan_mail_trades.py \
  --subject-keyword "交易訊號"
```

可用環境變數：

- `MAIL_IMAP_HOST`
- `MAIL_IMAP_PORT`（預設 `993`）
- `MAIL_IMAP_USER`
- `MAIL_IMAP_SECRET`

執行結果：

- `outputs/mail_trade_records.csv`
- `outputs/current_holdings.json`

`daily` 任務會優先使用 `outputs/current_holdings.json` 的持股資料，若不存在或格式錯誤才回退到 `config.yaml` 的 `trading_preferences.holdings`。

## 測試

```bash
python3 -m unittest discover -s scheduler/tests -p "test_*.py"
```

建議 smoke test 順序：

1. `--test-email`
2. `--test-job news`
3. `--test-job daily`
4. `--test-job monitor`

## 輸出檔案與契約

- 排程日誌：`logs/scheduler.log`
- PID：`scheduler/scheduler.pid`
- 新聞週報：`strategy/news_strategy_*.md`
- 每日計畫：`outputs/trading_plan_*.md`
- 盤中分析：`intraday/stock_analysis_{股票代號}_{YYYYMMDD}.md`
- 候選訊號 JSON：`outputs/candidates/daily_*.json`、`outputs/candidates/monitor_*.json`
- 候選訊號 Markdown：`outputs/candidates/daily_*.md`、`outputs/candidates/monitor_*.md`

盤中分析 frontmatter 必要欄位：

- `stock_code`
- `stock_name`
- `suggestion`（`buy`/`sell`/`watch`/`hold`）
- `score`
- `bullish_signals`（array）
- `bearish_signals`（array）
- `price_close`

## 常見問題排查

- CLI 成功但任務仍失敗：
  - 系統要求對應報告檔必須新產生，否則判定失敗。
- `monitor` 沒有發警報：
  - 可能是非交易日、非監控時段、推薦清單為空、或未達 `signal_threshold`。
- skill preflight 失敗：
  - 在 `strict` 模式下會直接失敗，請確認 `task_skill_map` 與 skill 路徑可用。
- SMTP 登入失敗：
  - 優先檢查 `SMTP_SENDER`、`SMTP_AUTH_SECRET` 是否有效，Gmail 請使用應用程式密碼。

## 注意事項

- 本系統輸出僅供研究與輔助決策，不構成任何投資建議。
- 若調整排程或風險參數，請先以 `--test-job` 驗證後再上線。
