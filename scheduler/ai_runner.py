"""
AI CLI 呼叫模組（provider-agnostic）
透過設定檔切換不同 CLI provider，支援 argv / stdin prompt 傳遞模式。
"""

import glob
import logging
import os
import shlex
import subprocess
import time
from datetime import date

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STRATEGY_DIR = os.path.join(PROJECT_ROOT, "strategy")
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")

DEFAULT_ALLOWED_TOOLS = "Bash,Read,Write,Glob,Grep,WebSearch,WebFetch"

DEFAULT_AI_CONFIG = {
    "provider": "claude",
    "timeout_minutes": {
        "news": 10,
        "daily": 15,
    },
    "retry": {
        "max_attempts": 2,
        "backoff_seconds": 3,
    },
    "claude": {
        "command": "claude",
        "mode": "argv",
        "prompt_arg": "-p",
        "extra_args": ["--allowedTools", DEFAULT_ALLOWED_TOOLS],
    },
    "custom": {
        "command_template": "",
        "mode": "argv",
        "shell": True,
    },
}


def _normalize_args(args):
    if args is None:
        return []
    if isinstance(args, str):
        return shlex.split(args)
    if isinstance(args, list):
        return args
    return list(args)


def _deep_merge(base, override):
    """遞迴合併 dict（override 優先）"""
    if not isinstance(base, dict):
        return override if override is not None else base
    if not isinstance(override, dict):
        return base

    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_ai_config(config):
    ai_cfg = config.get("ai", {}) if isinstance(config, dict) else {}
    return _deep_merge(DEFAULT_AI_CONFIG, ai_cfg)


def _task_timeout(ai_cfg, task_name, fallback_minutes):
    timeout_cfg = ai_cfg.get("timeout_minutes", {})
    if isinstance(timeout_cfg, dict):
        return timeout_cfg.get(task_name, fallback_minutes)
    return fallback_minutes


def _build_provider_command(ai_cfg, prompt):
    provider = ai_cfg.get("provider", "claude")

    if provider == "claude":
        claude_cfg = ai_cfg.get("claude", {})
        command = claude_cfg.get("command", "claude")
        mode = claude_cfg.get("mode", "argv")
        prompt_arg = claude_cfg.get("prompt_arg", "-p")
        extra_args = _normalize_args(claude_cfg.get("extra_args", []))

        if mode == "stdin":
            cmd = [command, *extra_args]
            return cmd, prompt, False

        cmd = [command]
        if prompt_arg:
            cmd.extend([prompt_arg, prompt])
        else:
            cmd.append(prompt)
        cmd.extend(extra_args)
        return cmd, None, False

    if provider == "codex":
        custom_cfg = ai_cfg.get("codex", {})
        mode = custom_cfg.get("mode", "argv")
        shell = bool(custom_cfg.get("shell", True))
        template = str(custom_cfg.get("command_template", "")).strip()

        if not template:
            raise ValueError("ai.custom.command_template 不可為空")

        if mode == "stdin":
            cmd = template
            if not shell:
                cmd = shlex.split(template)
            return cmd, prompt, shell

        if shell:
            rendered = template.replace("{prompt}", prompt)
            cmd = rendered
        else:
            # shell=False 時用 token 置換，避免 prompt 空白被切碎
            parts = shlex.split(template)
            cmd = [prompt if p == "{prompt}" else p for p in parts]
        return cmd, None, shell

    raise ValueError(f"不支援的 ai.provider: {provider}")


def _find_recent_output(glob_pattern, started_at):
    files = sorted(glob.glob(glob_pattern))
    candidates = []

    for path in files:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        # 允許少量時間差，避免檔案系統 timestamp 精度差異
        if mtime >= started_at - 2:
            candidates.append(path)

    if not candidates:
        return None
    return candidates[-1]


def run_ai_task(task_name, prompt, config, timeout_minutes):
    """
    執行 AI 任務（單一 provider，不跨 provider fallback）

    Returns:
        tuple: (success: bool, stdout: str, stderr: str)
    """
    ai_cfg = _resolve_ai_config(config)
    retry_cfg = ai_cfg.get("retry", {})
    max_attempts = max(1, int(retry_cfg.get("max_attempts", 2)))
    backoff_seconds = max(0, int(retry_cfg.get("backoff_seconds", 3)))
    provider = ai_cfg.get("provider", "claude")

    timeout_sec = int(timeout_minutes * 60)
    last_stdout = ""
    last_stderr = ""

    for attempt in range(1, max_attempts + 1):
        try:
            cmd, stdin_input, shell = _build_provider_command(ai_cfg, prompt)
        except Exception as e:
            logger.error(f"[{task_name}] provider 設定錯誤: {e}")
            return False, "", str(e)

        logger.info(
            f"[{task_name}] 執行 AI provider={provider} attempt={attempt}/{max_attempts}, "
            f"timeout={timeout_minutes}min"
        )

        try:
            result = subprocess.run(
                cmd,
                input=stdin_input,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                cwd=PROJECT_ROOT,
                shell=shell,
            )
        except subprocess.TimeoutExpired:
            last_stdout = ""
            last_stderr = f"Timeout after {timeout_minutes} minutes"
            logger.error(f"[{task_name}] AI 執行超時: {last_stderr}")
        except FileNotFoundError:
            last_stdout = ""
            last_stderr = f"CLI not found for provider={provider}"
            logger.error(f"[{task_name}] {last_stderr}")
        except Exception as e:
            last_stdout = ""
            last_stderr = str(e)
            logger.error(f"[{task_name}] AI 執行異常: {e}")
        else:
            last_stdout = result.stdout
            last_stderr = result.stderr

            if result.returncode == 0:
                logger.info(f"[{task_name}] AI 執行成功")
                return True, last_stdout, last_stderr

            logger.error(
                f"[{task_name}] AI 執行失敗 returncode={result.returncode}, "
                f"stderr={last_stderr[:500]}"
            )

        if attempt < max_attempts and backoff_seconds > 0:
            time.sleep(backoff_seconds)

    return False, last_stdout, last_stderr


def run_news_stock_picker(config):
    """
    執行新聞選股任務，並驗證 strategy 報告檔案是否產生
    """
    prompt = (
        "請執行新聞驅動台股選股策略分析。"
        "搜尋近一週的國內外重大新聞，分析對台股的影響，"
        "產出完整的選股策略報告，儲存至 strategy/ 資料夾。"
        "請直接執行，不需要詢問我任何問題。"
    )

    ai_cfg = _resolve_ai_config(config)
    timeout_minutes = _task_timeout(ai_cfg, "news", 10)
    started_at = time.time()
    success, stdout, stderr = run_ai_task("news", prompt, config, timeout_minutes)
    if not success:
        return False, stdout, stderr

    report = _find_recent_output(os.path.join(STRATEGY_DIR, "news_strategy_*.md"), started_at)
    if not report:
        err = "AI 任務成功但未找到新產生的新聞報告檔案 (strategy/news_strategy_*.md)"
        logger.error(err)
        return False, stdout, err

    return True, stdout, stderr


def run_tw_stock_analyzer(config, preferences):
    """
    執行台股每日分析任務，並驗證 trading_plan 檔案是否產生
    """
    risk_level = preferences.get("risk_level", "moderate")
    capital = preferences.get("capital", 1000000)
    trading_period = preferences.get("trading_period", "short")
    holdings = preferences.get("holdings", [])
    focus_sectors = preferences.get("focus_sectors", [])

    capital_wan = capital / 10000
    holdings_str = "、".join(holdings) if holdings else "無"
    sectors_str = "、".join(focus_sectors) if focus_sectors else "不限"

    prompt = (
        f"請執行台股每日分析。我的偏好如下：\n"
        f"- 風險偏好：{risk_level}\n"
        f"- 可用資金：{capital_wan} 萬元\n"
        f"- 交易週期：{trading_period}\n"
        f"- 目前持股：{holdings_str}\n"
        f"- 關注產業：{sectors_str}\n\n"
        f"請依序執行：\n"
        f"1. 抓取今日台股資料（fetch_twse_data.py）\n"
        f"2. 計算技術指標（calculate_indicators.py）\n"
        f"3. 產生交易計畫（generate_plan.py），使用上述偏好設定\n\n"
        f"請直接產出完整交易計畫，不需要詢問我任何問題。"
    )

    ai_cfg = _resolve_ai_config(config)
    timeout_minutes = _task_timeout(ai_cfg, "daily", 15)
    started_at = time.time()
    success, stdout, stderr = run_ai_task("daily", prompt, config, timeout_minutes)
    if not success:
        return False, stdout, stderr

    plan = _find_recent_output(os.path.join(OUTPUTS_DIR, "trading_plan_*.md"), started_at)
    if not plan:
        err = "AI 任務成功但未找到新產生的交易計畫檔案 (outputs/trading_plan_*.md)"
        logger.error(err)
        return False, stdout, err

    return True, stdout, stderr


def run_single_stock_analysis(stock_code):
    """
    執行單一個股技術分析（沿用既有 Python 腳本）
    """
    script_path = os.path.join(
        PROJECT_ROOT,
        ".claude",
        "skills",
        "single-stock-analyzer",
        "scripts",
        "analyze_single_stock.py",
    )

    cmd = ["python3", script_path, stock_code]
    logger.debug(f"執行個股分析: {stock_code}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_ROOT,
        )

        if result.returncode == 0:
            return True, result.stdout, result.stderr

        logger.error(f"個股分析失敗 ({stock_code}): {result.stderr[:200]}")
        return False, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error(f"個股分析超時 ({stock_code})")
        return False, "", "Timeout"
    except Exception as e:
        logger.error(f"個股分析異常 ({stock_code}): {e}")
        return False, "", str(e)


def find_latest_news_report(target_date=None):
    """依既有規則尋找新聞報告（先找當日，再找最新）"""
    if target_date is None:
        target_date = date.today()

    report_pattern = os.path.join(STRATEGY_DIR, f"news_strategy_{target_date.isoformat()}*")
    reports = glob.glob(report_pattern)
    if reports:
        return reports[0]

    all_reports = sorted(glob.glob(os.path.join(STRATEGY_DIR, "news_strategy_*.md")))
    if all_reports:
        return all_reports[-1]
    return None


def find_latest_trading_plan(target_date=None):
    """依既有規則尋找交易計畫（先找當日，再找最新）"""
    if target_date is None:
        target_date = date.today()

    date_str = target_date.strftime("%Y%m%d")
    report_path = os.path.join(OUTPUTS_DIR, f"trading_plan_{date_str}.md")
    if os.path.exists(report_path):
        return report_path

    report_path_alt = os.path.join(OUTPUTS_DIR, f"trading_plan_{target_date.isoformat().replace('-', '')}.md")
    if os.path.exists(report_path_alt):
        return report_path_alt

    all_plans = sorted(glob.glob(os.path.join(OUTPUTS_DIR, "trading_plan_*.md")))
    if all_plans:
        return all_plans[-1]
    return None
