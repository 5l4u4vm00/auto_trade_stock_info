# auto_trade_stock

台股自動化排程分析專案。系統會定時呼叫 AI CLI 產生策略/交易計畫，並透過 Email 寄送報告與盤中警報。

## 功能概覽

- 每週新聞選股：每週固定時間產生 `strategy/news_strategy_*.md`
- 每日交易計畫：交易日上午產生 `outputs/trading_plan_*.md`
- 盤中監控警報：交易時段內定期分析推薦標的並寄送買賣提醒
- Provider 可切換：支援 `claude` 與 `codex` CLI

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
├── docker/                   # container 啟動初始化
├── strategy/                 # 新聞選股報告輸出
├── outputs/                  # 每日交易計畫輸出（執行後產生）
├── intraday/                 # 盤中個股分析報告輸出（執行後產生）
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
mkdir -p intraday
```

## 設定

編輯 `scheduler/config.yaml`：

1. `email`：SMTP 主機、帳號、密碼（Gmail 建議使用應用程式密碼）、收件人
2. `ai`：設定 provider、逾時、重試策略與 CLI 參數
3. `trading_preferences`：資金、風險偏好、交易週期、持股、關注產業
4. `schedule`：三個排程任務時間
5. `signal_threshold`：盤中警報觸發門檻
6. `ai.skill_enforcement`：強制任務使用 skill 的驗證與同步策略

## Skill 強制模式

2026-02-14 調整方式：`news` / `daily` / `monitor` 任務啟用 skill preflight，缺少必要 skill 時會直接失敗（`strict`）。

設定位置：`scheduler/config.yaml` -> `ai.skill_enforcement`

```yaml
ai:
  skill_enforcement:
    enabled: true
    mode: "strict"
    repo_skill_roots:
      - ".claude/skills"
      - ".codex/skills"
    task_skill_map:
      news: "news-stock-picker"
      daily: "tw-stock-analyzer"
      monitor: "single-stock-analyzer"
    provider_home_map:
      claude: "/root/.claude/skills"
      codex: "/root/.codex/skills"
```

說明：

- `strict`：缺少 task 對應 skill、skill 同步失敗時，任務立即失敗
- `warn`：記錄警告後仍繼續執行一般 prompt
- 任務執行前會先檢查 skill，並將可用 skill 同步到 provider home（同名覆蓋）
- 2026-02-13 調整方式：若 `repo_skill_roots` 找不到必要 skill，會自動 fallback 到 `provider_home_map` 路徑查找
- 若在非 root 本機執行，且 provider home 設為 `/root/...`，系統會自動映射到目前使用者 home 路徑

## Docker Compose（無 host bind）

`docker-compose.yaml` 已改為容器內建設定與 named volumes，不再掛載：

- `./scheduler/config.yaml`
- `./logs`、`./outputs`、`./strategy`、`./intraday`
- `./.claude`、`${HOME}/.claude`、`${HOME}/.codex`

`scheduler/config.yaml` 會隨 image 打包，修改設定後需重新 build。

2026-02-13 調整方式：映像會內建 `.claude/`、`.codex/`，skill 同步發生在任務執行前（非容器啟動時）。

啟動方式：

```bash
docker compose up -d --build
```

### claude / codex 家目錄注入（可選）

若要在容器內保留 `~/.claude` 或 `~/.codex`（例如 provider 登入狀態），可先在主機打包並 base64：

```bash
tar -czf - -C "${HOME}" .claude/.credentials.json | base64 -w0
tar -czf - -C "${HOME}" .codex/auth.json | base64 -w0
```

再放入 `.env`：

```bash
CLAUDE_HOME_TGZ_B64=<上面輸出的單行字串>
CODEX_HOME_TGZ_B64=<上面輸出的單行字串>
```

未設定這兩個變數時，容器仍可啟動，只是不會還原對應 home 目錄資料。

### 容器內 terminal 操作（保留 `docker exec`）

2026-02-13 調整方式：`scheduler` 主容器保留互動終端，可在不停止排程下進入容器操作。

```bash
# 建議用 compose service 名稱進入
docker compose exec scheduler bash

# 或直接用容器名稱進入
docker exec -it auto-trade-scheduler bash
```

若映像調整後未包含 `bash`，可改用 `sh`：

```bash
docker compose exec scheduler sh
docker exec -it auto-trade-scheduler sh
```

若容器尚未啟動，先執行：

```bash
docker compose up -d --build
```

一次性檢查建議用 `bash -lc`，避免影響主進程：

```bash
docker compose exec scheduler bash -lc "whoami && pwd"
```

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
- Job 3（盤中監控）：週一到週五 `09:00-13:30`，每 `10` 分鐘

## 輸出與日誌

- 排程日誌：`logs/scheduler.log`
- PID 檔：`scheduler/scheduler.pid`
- 新聞策略：`strategy/news_strategy_*.md`
- 交易計畫：`outputs/trading_plan_*.md`
- 盤中個股報告：`intraday/stock_analysis_{股票代號}_{YYYYMMDD}.md`

盤中個股報告 YAML frontmatter 契約欄位：

- `stock_code`
- `stock_name`
- `suggestion`（buy/sell/watch/hold）
- `score`
- `bullish_signals`（array）
- `bearish_signals`（array）
- `price_close`

## 測試

```bash
python3 -m unittest discover -s scheduler/tests -p "test_*.py"
```

## 注意事項

- `scheduler/trading_calendar.py` 的假日清單目前為手動維護（含 2025、2026），每年需更新。
- `daily` / `news` 任務除了 CLI 回傳成功，還要求新報告檔案實際產生才視為成功。
- `monitor` 任務會強制使用 `single-stock-analyzer` skill，並要求輸出 Markdown + YAML frontmatter。

# Scheduler AI Provider 設定

本專案排程系統使用 `scheduler/ai_runner.py` 呼叫 AI CLI，透過 `scheduler/config.yaml` 的 `ai` 區塊切換 provider。

## 支援 provider

- `claude`：內建設定，預設可直接使用
- `codex`：透過 `command_template` 呼叫 Codex CLI

## 設定範例

```yaml
ai:
  provider: "claude"
  timeout_minutes:
    news: 10
    daily: 15
    monitor: 5
  retry:
    max_attempts: 2
    backoff_seconds: 3
  claude:
    command: "claude"
    mode: "argv"
    prompt_arg: "-p"
    extra_args:
      - "--allowedTools"
      - "Bash,Read,Write,Glob,Grep,WebSearch,WebFetch"
```

## `codex` provider（argv）

`command_template` 可使用 `{prompt}` 佔位符：

```yaml
ai:
  provider: "codex"
  codex:
    command_template: "my_ai_cli --model x1 --prompt '{prompt}'"
    mode: "argv"
    shell: true
```

## `codex` provider（stdin）

將 prompt 透過標準輸入傳遞：

```yaml
ai:
  provider: "codex"
  codex:
    command_template: "my_ai_cli --model x1"
    mode: "stdin"
    shell: true
```

## `codex` provider（Codex CLI 範例）

使用 Codex CLI，並在指令中指定版本：

```yaml
ai:
  provider: "codex"
  codex:
    command_template: "codex exec -m gpt-5-codex --full-auto --skip-git-repo-check"
    mode: "stdin"
    shell: true
```

說明：

- `-m gpt-5-codex`：指定 Codex 模型版本
- `mode: "stdin"`：由 `ai_runner` 將任務 prompt 透過 stdin 傳給 `codex exec`
- 若要切回 Claude，將 `provider` 改回 `"claude"` 即可

## 成功判定規則

- `news` 任務：CLI return code = 0 且有新產生 `strategy/news_strategy_*.md`
- `daily` 任務：CLI return code = 0 且有新產生 `outputs/trading_plan_*.md`
- `monitor` 任務：CLI return code = 0 且有新產生 `intraday/stock_analysis_*.md`
- 若只成功執行 CLI、但未產生檔案，任務仍視為失敗

# CMD ["python", "-u", "scheduler/main.py"]
