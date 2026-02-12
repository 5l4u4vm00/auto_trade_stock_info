# Scheduler AI Provider 設定

本專案排程系統使用 `scheduler/ai_runner.py` 呼叫 AI CLI，透過 `scheduler/config.yaml` 的 `ai` 區塊切換 provider。

## 支援 provider

- `claude`：內建設定，預設可直接使用
- `custom`：可自訂任意 CLI 指令模板

## 設定範例

```yaml
ai:
  provider: "claude"
  timeout_minutes:
    news: 10
    daily: 15
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

## `custom` provider（argv）

`command_template` 可使用 `{prompt}` 佔位符：

```yaml
ai:
  provider: "custom"
  custom:
    command_template: "my_ai_cli --model x1 --prompt '{prompt}'"
    mode: "argv"
    shell: true
```

## `custom` provider（stdin）

將 prompt 透過標準輸入傳遞：

```yaml
ai:
  provider: "custom"
  custom:
    command_template: "my_ai_cli --model x1"
    mode: "stdin"
    shell: true
```

## `custom` provider（Codex 範例）

使用 Codex CLI，並在指令中指定版本：

```yaml
ai:
  provider: "custom"
  custom:
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
- 若只成功執行 CLI、但未產生檔案，任務仍視為失敗
