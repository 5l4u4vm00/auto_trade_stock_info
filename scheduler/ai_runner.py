"""
AI CLI 呼叫模組（provider-agnostic）
透過設定檔切換不同 CLI provider，支援 argv / stdin prompt 傳遞模式。
"""

import glob
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import time
from datetime import date

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STRATEGY_DIR = os.path.join(PROJECT_ROOT, "strategy")
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")
INTRADAY_DIR = os.path.join(PROJECT_ROOT, "intraday")

DEFAULT_ALLOWED_TOOLS = "Bash,Read,Write,Glob,Grep,WebSearch,WebFetch"

DEFAULT_AI_CONFIG = {
    "provider": "claude",
    "timeout_minutes": {
        "news": 10,
        "daily": 15,
        "monitor": 5,
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
    "codex": {
        "command_template": "",
        "mode": "argv",
        "shell": True,
    },
    "skill_enforcement": {
        "enabled": True,
        "mode": "strict",  # strict / warn
        "repo_skill_roots": [
            "/root/.claude/skills",
            "/root/.codex/skills",
        ],
        "task_skill_map": {
            "news": "news-stock-picker",
            "daily": "tw-stock-analyzer",
            "monitor": "multi-stock-analyzer",
            "monitor_single": "single-stock-analyzer",
        },
        "provider_home_map": {
            "claude": "/root/.claude/skills",
            "codex": "/root/.codex/skills",
        },
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


def _resolve_skill_config(ai_cfg):
    skill_cfg = ai_cfg.get("skill_enforcement", {})
    return _deep_merge(DEFAULT_AI_CONFIG["skill_enforcement"], skill_cfg)


def _is_strict_skill_mode(skill_cfg):
    mode = str(skill_cfg.get("mode", "strict")).strip().lower()
    return mode != "warn"


def _iter_repo_skill_roots(skill_cfg, provider):
    roots = skill_cfg.get("repo_skill_roots", [])
    if not isinstance(roots, list):
        return []

    preferred_root = f".{provider}/skills"
    resolved_roots = []

    for root in roots:
        root_path = str(root).strip()
        if not root_path:
            continue
        if not os.path.isabs(root_path):
            root_path = os.path.join(PROJECT_ROOT, root_path)
        resolved_roots.append(os.path.abspath(root_path))

    preferred = []
    others = []

    for root_path in resolved_roots:
        if preferred_root in root_path:
            preferred.append(root_path)
            continue
        others.append(root_path)

    return [*preferred, *others]


def _resolve_provider_skill_home(provider, skill_cfg):
    provider_home_map = skill_cfg.get("provider_home_map", {})
    if not isinstance(provider_home_map, dict):
        return "", "ai.skill_enforcement.provider_home_map 設定格式錯誤"

    raw_path = str(provider_home_map.get(provider, "")).strip()
    if not raw_path:
        return "", f"ai.skill_enforcement.provider_home_map 未定義 provider: {provider}"

    resolved_path = os.path.abspath(os.path.expanduser(raw_path))
    current_home = os.path.abspath(os.path.expanduser("~"))

    # 2026-02-13 調整方式: 當非 root 執行且設定為 /root 路徑時，自動映射為目前使用者 home。
    if resolved_path.startswith("/root/") and current_home != "/root":
        relative_path = os.path.relpath(resolved_path, "/root")
        resolved_path = os.path.join(current_home, relative_path)

    return resolved_path, ""


def _iter_skill_source_roots(skill_cfg, provider):
    repo_roots = _iter_repo_skill_roots(skill_cfg, provider)
    source_roots = []

    for root_path in repo_roots:
        if root_path in source_roots:
            continue
        source_roots.append(root_path)

    provider_home_dir, error_message = _resolve_provider_skill_home(provider, skill_cfg)
    if error_message:
        return source_roots, error_message, ""

    # 2026-02-13 調整方式: repo skill roots 找不到時，自動 fallback provider home 路徑。
    if provider_home_dir not in source_roots:
        source_roots.append(provider_home_dir)

    return source_roots, "", provider_home_dir


def _find_skill_path(skill_name, source_roots):
    for root_path in source_roots:
        skill_dir = os.path.join(root_path, skill_name)
        skill_file = os.path.join(skill_dir, "SKILL.md")
        if os.path.isdir(skill_dir) and os.path.isfile(skill_file):
            return skill_dir

    return ""


def _collect_repo_skill_map(skill_cfg, provider):
    skill_map = {}
    source_roots, error_message, _ = _iter_skill_source_roots(skill_cfg, provider)
    if error_message:
        return {}, error_message

    for root_path in source_roots:
        if not os.path.isdir(root_path):
            continue

        for entry in os.listdir(root_path):
            if entry in skill_map:
                continue

            skill_dir = os.path.join(root_path, entry)
            skill_file = os.path.join(skill_dir, "SKILL.md")
            if not os.path.isdir(skill_dir):
                continue
            if not os.path.isfile(skill_file):
                continue
            skill_map[entry] = skill_dir

    return skill_map, ""


def _validate_required_skill(task_name, provider, skill_cfg):
    task_skill_map = skill_cfg.get("task_skill_map", {})
    if not isinstance(task_skill_map, dict):
        return False, {}, "ai.skill_enforcement.task_skill_map 設定格式錯誤"

    skill_name = str(task_skill_map.get(task_name, "")).strip()
    if not skill_name:
        return False, {}, f"task_skill_map 未定義: {task_name}"

    source_roots, error_message, provider_home_dir = _iter_skill_source_roots(
        skill_cfg, provider
    )
    if error_message:
        return False, {}, error_message

    repo_skill_dir = _find_skill_path(skill_name, source_roots)
    if not repo_skill_dir:
        return False, {}, f"缺少必要 skill: {skill_name}"

    return (
        True,
        {
            "skill_name": skill_name,
            "repo_skill_dir": repo_skill_dir,
            "provider_home_dir": provider_home_dir,
        },
        "",
    )


def _sync_repo_skills_to_provider_home(provider, skill_cfg):
    provider_home_dir, error_message = _resolve_provider_skill_home(provider, skill_cfg)
    if error_message:
        return {}, error_message

    repo_skill_map, collect_error = _collect_repo_skill_map(skill_cfg, provider)
    if collect_error:
        return {}, collect_error
    if not repo_skill_map:
        return {}, "repo_skill_roots 下找不到可用 skill"

    try:
        os.makedirs(provider_home_dir, exist_ok=True)
    except Exception as e:
        return {}, f"無法建立 provider skill 目錄: {provider_home_dir}, error: {e}"

    synced_skill_map = {}

    for skill_name, source_dir in repo_skill_map.items():
        target_dir = os.path.join(provider_home_dir, skill_name)
        try:
            normalized_source = os.path.abspath(source_dir)
            normalized_target = os.path.abspath(target_dir)
            # 2026-02-13 調整方式: source 與 target 同路徑時跳過覆蓋，避免自刪除。
            if normalized_source != normalized_target:
                if os.path.isdir(target_dir):
                    shutil.rmtree(target_dir)
                shutil.copytree(source_dir, target_dir)
        except Exception as e:
            return {}, f"無法同步 skill 至 provider home: {target_dir}, error: {e}"

        synced_skill_map[skill_name] = target_dir

    return synced_skill_map, ""


def _build_skill_enforced_prompt(
    task_name, base_prompt, skill_name, repo_skill_dir, provider_skill_dir
):
    return (
        "【Skill 強制規則】\n"
        f"- 任務類型：{task_name}\n"
        f"- 本次任務必須使用 skill：{skill_name}\n"
        f"- 專案 skill 路徑：{repo_skill_dir}\n"
        f"- Provider home skill 路徑：{provider_skill_dir}\n"
        "- 請先讀取該 skill 的 SKILL.md 並嚴格遵循其 workflow。\n"
        "- 若無法載入 skill，必須立即回報錯誤並停止，不可改用一般流程。\n\n"
        "【原始任務】\n"
        f"{base_prompt}"
    )


def _prepare_task_prompt(task_name, base_prompt, ai_cfg):
    skill_cfg = _resolve_skill_config(ai_cfg)
    if not bool(skill_cfg.get("enabled", True)):
        return True, base_prompt, ""

    provider = str(ai_cfg.get("provider", "claude")).strip()
    is_strict_mode = _is_strict_skill_mode(skill_cfg)

    is_valid, context, error_message = _validate_required_skill(
        task_name, provider, skill_cfg
    )
    if not is_valid:
        if is_strict_mode:
            logger.error(f"[{task_name}] skill preflight 失敗: {error_message}")
            return False, "", error_message
        logger.warning(
            f"[{task_name}] skill preflight 警告，改用一般流程: {error_message}"
        )
        return True, base_prompt, ""

    synced_skill_map, sync_error = _sync_repo_skills_to_provider_home(
        provider, skill_cfg
    )
    if sync_error:
        if is_strict_mode:
            logger.error(f"[{task_name}] skill 同步失敗: {sync_error}")
            return False, "", sync_error
        logger.warning(f"[{task_name}] skill 同步警告，改用一般流程: {sync_error}")
        return True, base_prompt, ""

    skill_name = context["skill_name"]
    provider_skill_dir = synced_skill_map.get(skill_name, "")
    if not provider_skill_dir:
        error_message = f"無法取得 provider skill 路徑: {skill_name}"
        if is_strict_mode:
            logger.error(f"[{task_name}] {error_message}")
            return False, "", error_message
        logger.warning(f"[{task_name}] {error_message}，改用一般流程")
        return True, base_prompt, ""

    logger.info(
        f"[{task_name}] skill preflight 成功: skill={skill_name}, provider={provider}, "
        f"repo={context['repo_skill_dir']}, provider_home={provider_skill_dir}"
    )

    prompt = _build_skill_enforced_prompt(
        task_name,
        base_prompt,
        skill_name,
        context["repo_skill_dir"],
        provider_skill_dir,
    )
    return True, prompt, ""


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
        codex_cfg = ai_cfg.get("codex", {})
        mode = codex_cfg.get("mode", "argv")
        shell = bool(codex_cfg.get("shell", True))
        template = str(codex_cfg.get("command_template", "")).strip()

        if not template:
            raise ValueError("ai.codex.command_template 不可為空")

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
    can_run, prompt, error_message = _prepare_task_prompt("news", prompt, ai_cfg)
    if not can_run:
        return False, "", error_message

    timeout_minutes = _task_timeout(ai_cfg, "news", 10)
    started_at = time.time()
    success, stdout, stderr = run_ai_task("news", prompt, config, timeout_minutes)
    if not success:
        return False, stdout, stderr

    report = _find_recent_output(
        os.path.join(STRATEGY_DIR, "news_strategy_*.md"), started_at
    )
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
    can_run, prompt, error_message = _prepare_task_prompt("daily", prompt, ai_cfg)
    if not can_run:
        return False, "", error_message

    timeout_minutes = _task_timeout(ai_cfg, "daily", 15)
    started_at = time.time()
    success, stdout, stderr = run_ai_task("daily", prompt, config, timeout_minutes)
    if not success:
        return False, stdout, stderr

    plan = _find_recent_output(
        os.path.join(OUTPUTS_DIR, "trading_plan_*.md"), started_at
    )
    if not plan:
        err = "AI 任務成功但未找到新產生的交易計畫檔案 (outputs/trading_plan_*.md)"
        logger.error(err)
        return False, stdout, err

    return True, stdout, stderr


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_signal_list(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _build_intraday_multi_monitor_prompt(stock_codes):
    stock_code_list = " ".join(stock_codes)
    return (
        f"請針對以下股票一次執行盤中技術分析：{stock_code_list}\n"
        "請強制使用 multi-stock-analyzer skill，並依其 workflow 執行批次腳本。\n"
        "輸出要求：\n"
        "1. 回覆內容僅限 JSON。\n"
        "2. 不可輸出 Markdown、程式碼區塊或其他說明文字。\n"
        "3. JSON 需包含 results 與 failed_symbols 欄位。\n"
        "請直接執行，不需要再提問。"
    )


def _parse_multi_stock_stdout(raw_text):
    if not raw_text:
        return None

    candidates = [raw_text.strip()]
    json_block_match = re.search(
        r"```json\s*(\{.*?\})\s*```",
        raw_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if json_block_match:
        candidates.append(json_block_match.group(1).strip())

    first_brace_index = raw_text.find("{")
    last_brace_index = raw_text.rfind("}")
    if first_brace_index >= 0 and last_brace_index > first_brace_index:
        candidates.append(raw_text[first_brace_index:last_brace_index + 1].strip())

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data

    return None


def _normalize_multi_stock_result(result_item):
    if not isinstance(result_item, dict):
        return None

    stock_code = str(result_item.get("stock_code", "")).strip()
    if not stock_code:
        return None

    price_data = result_item.get("price", {})
    if not isinstance(price_data, dict):
        price_data = {}

    bullish_signals = _normalize_signal_list(result_item.get("bullish_signals", []))
    bearish_signals = _normalize_signal_list(result_item.get("bearish_signals", []))

    return {
        "stock_code": stock_code,
        "stock_name": str(result_item.get("stock_name", "")).strip(),
        "price": _safe_float(price_data.get("close", 0)),
        "suggestion": str(result_item.get("suggestion", "")).strip().lower(),
        "score": _safe_int(result_item.get("score", 0)),
        "bullish_count": len(bullish_signals),
        "bearish_count": len(bearish_signals),
        "bullish_signals": bullish_signals,
        "bearish_signals": bearish_signals,
        "error": False,
    }


def run_multi_stock_analysis(stock_codes, config=None):
    """
    執行多檔個股技術分析（透過 multi-stock-analyzer skill）

    Args:
        stock_codes: 股票代號清單
        config: scheduler 設定 dict（可選）
    """
    normalized_stock_codes = []
    seen_codes = set()
    for stock_code in stock_codes or []:
        stock_code_text = str(stock_code).strip()
        if not stock_code_text or stock_code_text in seen_codes:
            continue
        seen_codes.add(stock_code_text)
        normalized_stock_codes.append(stock_code_text)

    if not normalized_stock_codes:
        return False, [], "stock_codes 不可為空"

    runtime_config = config or {}
    ai_cfg = _resolve_ai_config(runtime_config)
    timeout_minutes = _task_timeout(ai_cfg, "monitor", 5)
    prompt = _build_intraday_multi_monitor_prompt(normalized_stock_codes)

    can_run, prompt, error_message = _prepare_task_prompt("monitor", prompt, ai_cfg)
    if not can_run:
        return False, [], error_message

    # 2026-02-14 調整方式: monitor 改為 multi-stock skill 一次分析多檔並回傳 JSON。
    success, stdout, stderr = run_ai_task(
        "monitor",
        prompt,
        runtime_config,
        timeout_minutes,
    )
    if not success:
        return False, [], stderr

    raw_result = _parse_multi_stock_stdout(stdout)
    if not raw_result:
        error_message = f"批次分析輸出無法解析 JSON: {stdout[:200]}"
        logger.error(error_message)
        return False, [], error_message

    raw_items = raw_result.get("results", [])
    if not isinstance(raw_items, list):
        raw_items = []

    parsed_results = []
    for raw_item in raw_items:
        parsed_item = _normalize_multi_stock_result(raw_item)
        if parsed_item:
            parsed_results.append(parsed_item)

    failed_items = raw_result.get("failed_symbols", [])
    if isinstance(failed_items, list) and failed_items:
        logger.warning(f"批次分析失敗標的數量: {len(failed_items)}")

    if parsed_results:
        return True, parsed_results, stderr

    failure_message = str(raw_result.get("message", "")).strip()
    if not failure_message:
        failure_message = "AI 任務完成但沒有可用個股分析結果"
    logger.error(failure_message)
    return False, [], failure_message


def _build_intraday_monitor_prompt(stock_code, report_path):
    return (
        f"請針對個股 {stock_code} 執行盤中技術分析。\n"
        f"請強制使用 single-stock-analyzer skill 完成分析。\n"
        f"輸出檔案必須儲存為：{report_path}\n\n"
        "報告內容請遵循下列格式要求：\n"
        "1. 檔案格式為 Markdown。\n"
        "2. 最上方必須放 YAML frontmatter（使用 --- 包覆）。\n"
        "3. frontmatter 必須包含：\n"
        "   - stock_code\n"
        "   - stock_name\n"
        "   - suggestion（buy/sell/watch/hold）\n"
        "   - score（整數）\n"
        "   - bullish_signals（字串陣列）\n"
        "   - bearish_signals（字串陣列）\n"
        "   - price_close（數字）\n\n"
        "請直接執行並寫入指定檔案，不需要再提問。"
    )


def _find_recent_intraday_report(stock_code, report_date, started_at):
    today_pattern = os.path.join(
        INTRADAY_DIR, f"stock_analysis_{stock_code}_{report_date}*.md"
    )
    report_path = _find_recent_output(today_pattern, started_at)
    if report_path:
        return report_path

    fallback_pattern = os.path.join(INTRADAY_DIR, f"stock_analysis_{stock_code}_*.md")
    return _find_recent_output(fallback_pattern, started_at)


def run_single_stock_analysis(stock_code, config=None):
    """
    執行單一個股技術分析（透過 single-stock-analyzer skill）

    Args:
        stock_code: 股票代號
        config: scheduler 設定 dict（可選）
    """
    normalized_stock_code = str(stock_code).strip()
    if not normalized_stock_code:
        return False, "", "stock_code 不可為空"

    runtime_config = config or {}
    ai_cfg = _resolve_ai_config(runtime_config)
    timeout_minutes = _task_timeout(ai_cfg, "monitor", 5)

    os.makedirs(INTRADAY_DIR, exist_ok=True)

    report_date = date.today().strftime("%Y%m%d")
    target_report_path = os.path.join(
        INTRADAY_DIR,
        f"stock_analysis_{normalized_stock_code}_{report_date}.md",
    )
    prompt = _build_intraday_monitor_prompt(normalized_stock_code, target_report_path)

    can_run, prompt, error_message = _prepare_task_prompt(
        "monitor_single",
        prompt,
        ai_cfg,
    )
    if not can_run:
        return False, "", error_message

    # 2026-02-14 調整方式: monitor 改為 skill 流程並固定輸出到專案根目錄 intraday/。
    started_at = time.time()
    success, stdout, stderr = run_ai_task(
        "monitor",
        prompt,
        runtime_config,
        timeout_minutes,
    )
    if not success:
        return False, stdout, stderr

    report_path = _find_recent_intraday_report(
        normalized_stock_code,
        report_date,
        started_at,
    )
    if not report_path:
        error_message = (
            "AI 任務成功但未找到新產生的個股分析檔案 "
            f"(intraday/stock_analysis_{normalized_stock_code}_*.md)"
        )
        logger.error(error_message)
        return False, stdout, error_message

    try:
        with open(report_path, "r", encoding="utf-8") as file_obj:
            report_content = file_obj.read()
    except Exception as exc:
        error_message = f"讀取個股分析報告失敗: {report_path}, error: {exc}"
        logger.error(error_message)
        return False, stdout, error_message

    return True, report_content, stderr


def find_latest_news_report(target_date=None):
    """依既有規則尋找新聞報告（先找當日，再找最新）"""
    if target_date is None:
        target_date = date.today()

    report_pattern = os.path.join(
        STRATEGY_DIR, f"news_strategy_{target_date.isoformat()}*"
    )
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

    report_path_alt = os.path.join(
        OUTPUTS_DIR, f"trading_plan_{target_date.isoformat().replace('-', '')}.md"
    )
    if os.path.exists(report_path_alt):
        return report_path_alt

    all_plans = sorted(glob.glob(os.path.join(OUTPUTS_DIR, "trading_plan_*.md")))
    if all_plans:
        return all_plans[-1]
    return None
