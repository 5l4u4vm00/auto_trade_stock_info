#!/usr/bin/env python3
"""
多檔個股快速技術分析腳本
用法: python3 analyze_multi_stock.py <股票代號或名稱清單>
輸出: JSON 格式批次分析結果到 stdout

變更紀錄:
- 2026-02-14: 新增多檔批次分析腳本，重用 single-stock-analyzer 的核心邏輯。
"""

import importlib.util
import json
import os
import re
import sys
from datetime import datetime


MAX_BATCH_SIZE = 10
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
SINGLE_SCRIPT_PATH = os.path.join(
    PROJECT_ROOT,
    ".codex",
    "skills",
    "single-stock-analyzer",
    "scripts",
    "analyze_single_stock.py",
)


def parse_inputs(raw_args):
    """將 argv 解析為股票清單，支援空白與逗號分隔。"""
    combined_text = " ".join(raw_args).strip()
    if not combined_text:
        return []
    return [part.strip() for part in re.split(r"[\s,]+", combined_text) if part.strip()]


def deduplicate_keep_order(values):
    """去重複並保留原始順序。"""
    unique_values = []
    seen_values = set()
    for value in values:
        if value in seen_values:
            continue
        seen_values.add(value)
        unique_values.append(value)
    return unique_values


def build_error_response(message, hint=None, examples=None):
    """建立一致格式的錯誤輸出。"""
    response = {
        "error": True,
        "message": message,
    }
    if hint:
        response["hint"] = hint
    if examples:
        response["examples"] = examples
    return response


def load_single_stock_module():
    """動態載入 single-stock-analyzer 腳本作為可重用模組。"""
    if not os.path.exists(SINGLE_SCRIPT_PATH):
        raise FileNotFoundError(f"找不到 single-stock-analyzer 腳本: {SINGLE_SCRIPT_PATH}")

    module_spec = importlib.util.spec_from_file_location("single_stock_module", SINGLE_SCRIPT_PATH)
    if module_spec is None or module_spec.loader is None:
        raise ImportError("無法建立 single-stock-analyzer 模組載入規格")

    single_stock_module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(single_stock_module)
    return single_stock_module


def analyze_single_input(stock_input, single_module):
    """分析單一輸入標的，回傳 (result, failed_item)。"""
    try:
        stock_code, stock_name = single_module.resolve_stock_code(stock_input)
        if not stock_code:
            failed_item = {
                "input": stock_input,
                "resolved_code": "",
                "reason": "無法辨識股票代號或名稱",
            }
            return None, failed_item

        historical_data, market = single_module.get_historical_data(stock_code)
        if historical_data is None or len(historical_data) < 5:
            failed_item = {
                "input": stock_input,
                "resolved_code": stock_code,
                "reason": "無法取得足夠歷史資料",
            }
            return None, failed_item

        if not stock_name:
            stock_name = stock_code

        analysis_result = single_module.analyze(stock_code, stock_name, historical_data, market)
        analysis_result["error"] = False
        analysis_result["input"] = stock_input
        return analysis_result, None
    except Exception as exception:  # noqa: BLE001
        failed_item = {
            "input": stock_input,
            "resolved_code": "",
            "reason": f"分析過程發生例外: {str(exception)}",
        }
        return None, failed_item


def sort_results(results):
    """依 score 由高到低排序，同分依漲跌幅由高到低。"""
    return sorted(
        results,
        key=lambda item: (
            item.get("score", -999),
            item.get("price", {}).get("change_pct", -999),
        ),
        reverse=True,
    )


def build_success_response(requested_symbols, normalized_symbols, results, failed_symbols, started_at):
    """建立批次分析成功輸出。"""
    analyzed_count = len(results)
    failed_count = len(failed_symbols)
    has_success = analyzed_count > 0

    if has_success:
        message = f"批次分析完成：成功 {analyzed_count} 檔，失敗 {failed_count} 檔。"
    else:
        message = "批次分析完成，但沒有可用的成功標的。"

    return {
        "error": not has_success,
        "message": message,
        "requested_symbols": requested_symbols,
        "normalized_symbols": normalized_symbols,
        "max_batch_size": MAX_BATCH_SIZE,
        "sorted_by": "score_desc,change_pct_desc",
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "analyzed_count": analyzed_count,
        "failed_count": failed_count,
        "results": results,
        "failed_symbols": failed_symbols,
    }


def main():
    if len(sys.argv) < 2:
        response = build_error_response(
            message="請提供至少一檔股票。用法: python3 analyze_multi_stock.py <股票清單>",
            hint="可用空白或逗號分隔，例如 2330 2317 2454 或 2330,2317,2454",
            examples=[
                "python3 analyze_multi_stock.py 2330 2317 2454",
                "python3 analyze_multi_stock.py 台積電 鴻海 聯發科",
            ],
        )
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 1

    requested_symbols = parse_inputs(sys.argv[1:])
    if not requested_symbols:
        response = build_error_response(
            message="沒有解析到有效輸入。",
            hint="請輸入股票代號或名稱，例如 2330 2317 2454",
        )
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 1

    normalized_symbols = deduplicate_keep_order(requested_symbols)
    if len(normalized_symbols) > MAX_BATCH_SIZE:
        response = build_error_response(
            message=f"單次最多分析 {MAX_BATCH_SIZE} 檔，目前收到 {len(normalized_symbols)} 檔。",
            hint="請分批執行，例如每批 5-10 檔。",
        )
        response["requested_symbols"] = requested_symbols
        response["normalized_symbols"] = normalized_symbols
        response["max_batch_size"] = MAX_BATCH_SIZE
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 1

    try:
        single_module = load_single_stock_module()
    except Exception as exception:  # noqa: BLE001
        response = build_error_response(
            message="載入 single-stock-analyzer 失敗。",
            hint=f"{str(exception)}。請先安裝 pandas / numpy / yfinance（例如: python3 -m pip install pandas numpy yfinance）",
        )
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 1

    started_at = datetime.now().isoformat(timespec="seconds")
    results = []
    failed_symbols = []

    for stock_input in normalized_symbols:
        analysis_result, failed_item = analyze_single_input(stock_input, single_module)
        if analysis_result is not None:
            results.append(analysis_result)
            continue
        failed_symbols.append(failed_item)

    sorted_results = sort_results(results)
    response = build_success_response(
        requested_symbols=requested_symbols,
        normalized_symbols=normalized_symbols,
        results=sorted_results,
        failed_symbols=failed_symbols,
        started_at=started_at,
    )
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response["analyzed_count"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
