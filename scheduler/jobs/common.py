"""排程任務共用工具。"""

import json
import logging
import os
from datetime import datetime

try:
    from reporting.report_writer import write_candidates_json, write_candidates_markdown
except ModuleNotFoundError:  # pragma: no cover
    from scheduler.reporting.report_writer import (  # type: ignore
        write_candidates_json,
        write_candidates_markdown,
    )

SCHEDULER_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCHEDULER_DIR, "..", ".."))
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")
CANDIDATE_DIR = os.path.join(OUTPUTS_DIR, "candidates")

logger = logging.getLogger("scheduler")


def _build_run_id(job_name):
    now = datetime.now()
    return f"{job_name}_{now.strftime('%Y%m%d%H%M%S')}"


def _log_job_event(job_name, run_id, event_name, **payload):
    event_payload = {
        "job": job_name,
        "run_id": run_id,
        "event": event_name,
        **payload,
    }
    logger.info(f"job_event={json.dumps(event_payload, ensure_ascii=False)}")


def _write_candidate_outputs(job_name, run_id, run_datetime, candidates):
    """輸出候選訊號 JSON/Markdown。"""
    # 2026-02-15 調整方式: 抽離 main.py 內共用輸出流程至 jobs.common。
    timestamp_text = run_datetime.strftime("%Y%m%d_%H%M")
    output_prefix = os.path.join(CANDIDATE_DIR, f"{job_name}_{timestamp_text}")

    metadata = {
        "job": job_name,
        "run_id": run_id,
        "candidate_count": len(candidates),
    }

    json_path = write_candidates_json(candidates, f"{output_prefix}.json", metadata)
    markdown_path = write_candidates_markdown(
        candidates,
        f"{output_prefix}.md",
        metadata,
    )
    return [json_path, markdown_path]

