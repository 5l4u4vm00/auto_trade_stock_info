"""
Claude CLI 呼叫模組
封裝 claude -p 非互動模式呼叫邏輯

Deprecated:
  請改用 scheduler/ai_runner.py（provider-agnostic CLI 架構）
"""

import logging
import subprocess
import os

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

ALLOWED_TOOLS = "Bash,Read,Write,Glob,Grep,WebSearch,WebFetch"


def run_claude(prompt, timeout_minutes=10):
    """
    使用 claude CLI 非互動模式執行指定 prompt

    Args:
        prompt: 要傳給 claude 的完整 prompt
        timeout_minutes: 超時時間（分鐘）

    Returns:
        tuple: (success: bool, stdout: str, stderr: str)
    """
    cmd = [
        "claude",
        "-p", prompt,
        "--allowedTools", ALLOWED_TOOLS,
    ]

    timeout_sec = timeout_minutes * 60
    logger.info(f"執行 claude CLI (timeout={timeout_minutes}min)")
    logger.debug(f"Prompt: {prompt[:200]}...")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=PROJECT_ROOT,
        )

        if result.returncode == 0:
            logger.info("claude CLI 執行成功")
            logger.debug(f"stdout 長度: {len(result.stdout)}")
            return True, result.stdout, result.stderr
        else:
            logger.error(f"claude CLI 執行失敗 (returncode={result.returncode})")
            logger.error(f"stderr: {result.stderr[:500]}")
            return False, result.stdout, result.stderr

    except subprocess.TimeoutExpired:
        logger.error(f"claude CLI 執行超時 ({timeout_minutes} 分鐘)")
        return False, "", f"Timeout after {timeout_minutes} minutes"
    except FileNotFoundError:
        logger.error("找不到 claude CLI，請確認已安裝並在 PATH 中")
        return False, "", "claude CLI not found"
    except Exception as e:
        logger.error(f"claude CLI 執行異常: {e}")
        return False, "", str(e)


def run_news_stock_picker():
    """
    執行新聞選股 skill

    Returns:
        tuple: (success: bool, stdout: str, stderr: str)
    """
    prompt = (
        "請執行新聞驅動台股選股策略分析。"
        "搜尋近一週的國內外重大新聞，分析對台股的影響，"
        "產出完整的選股策略報告，儲存至 strategy/ 資料夾。"
        "請直接執行，不需要詢問我任何問題。"
    )
    return run_claude(prompt, timeout_minutes=10)


def run_tw_stock_analyzer(preferences):
    """
    執行台股每日分析 skill

    Args:
        preferences: dict with keys: risk_level, capital, trading_period, holdings, focus_sectors

    Returns:
        tuple: (success: bool, stdout: str, stderr: str)
    """
    risk_level = preferences.get('risk_level', 'moderate')
    capital = preferences.get('capital', 1000000)
    trading_period = preferences.get('trading_period', 'short')
    holdings = preferences.get('holdings', [])
    focus_sectors = preferences.get('focus_sectors', [])

    # 將資金從台幣轉換為萬元（generate_plan.py 使用萬元單位）
    capital_wan = capital / 10000

    holdings_str = '、'.join(holdings) if holdings else '無'
    sectors_str = '、'.join(focus_sectors) if focus_sectors else '不限'

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
    return run_claude(prompt, timeout_minutes=15)


def run_single_stock_analysis(stock_code):
    """
    執行單一個股技術分析（直接呼叫 Python 腳本）

    Args:
        stock_code: 股票代號（如 "2330"）

    Returns:
        tuple: (success: bool, stdout: str, stderr: str)
    """
    script_path = os.path.join(
        PROJECT_ROOT,
        '.claude', 'skills', 'single-stock-analyzer', 'scripts',
        'analyze_single_stock.py'
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
        else:
            logger.error(f"個股分析失敗 ({stock_code}): {result.stderr[:200]}")
            return False, result.stdout, result.stderr

    except subprocess.TimeoutExpired:
        logger.error(f"個股分析超時 ({stock_code})")
        return False, "", "Timeout"
    except Exception as e:
        logger.error(f"個股分析異常 ({stock_code}): {e}")
        return False, "", str(e)
