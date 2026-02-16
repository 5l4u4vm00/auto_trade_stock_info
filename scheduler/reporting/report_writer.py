"""候選訊號輸出工具。"""

import json
from datetime import datetime
from pathlib import Path


def _serialize_candidates(candidates):
    return [candidate.to_dict() for candidate in candidates]


def write_candidates_json(candidates, output_path, metadata=None):
    """輸出候選訊號 JSON 檔案。"""
    # 2026-02-15 調整方式: 新增統一 JSON 契約輸出，便於後續回測與審計。
    output_obj = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "metadata": metadata or {},
        "candidates": _serialize_candidates(candidates),
    }

    path_obj = Path(output_path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    with path_obj.open("w", encoding="utf-8") as file_obj:
        json.dump(output_obj, file_obj, ensure_ascii=False, indent=2)

    return str(path_obj)


def write_candidates_markdown(candidates, output_path, metadata=None):
    """輸出候選訊號 Markdown 檔案。"""
    # 2026-02-15 調整方式: 與 JSON 同步產出人類可讀版本，提供每日檢核。
    lines = []
    lines.append("# Candidate Signals")
    lines.append("")
    lines.append(f"- generated_at: {datetime.now().isoformat(timespec='seconds')}")

    if metadata:
        for key, value in metadata.items():
            lines.append(f"- {key}: {value}")

    lines.append("")
    lines.append(
        "| stock_code | action | total_score | confidence | technical | news | risk_penalty |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|")

    for candidate in candidates:
        data = candidate.to_dict()
        lines.append(
            f"| {data['stock_code']} | {data['action']} | {data['total_score']} "
            f"| {data['confidence']} | {data['technical_score']} "
            f"| {data['news_score']} | {data['risk_penalty']} |"
        )

    lines.append("")
    lines.append("## Reasons")
    lines.append("")

    for candidate in candidates:
        data = candidate.to_dict()
        reason_text = "; ".join(data.get("reasons", []))
        lines.append(f"- {data['stock_code']}: {reason_text}")

    path_obj = Path(output_path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text("\n".join(lines), encoding="utf-8")
    return str(path_obj)
