"""PID 檔案管理。"""

import logging
import os
import sys

SCHEDULER_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.abspath(os.path.join(SCHEDULER_DIR, "..", "scheduler.pid"))

logger = logging.getLogger("scheduler")


def check_pid(pid_file=PID_FILE):
    """檢查是否已有排程程式在執行。"""
    # 2026-02-15 調整方式: 從 main.py 抽離 PID 管理，避免入口層過大。
    if os.path.exists(pid_file):
        with open(pid_file, "r", encoding="utf-8") as file_obj:
            old_pid = file_obj.read().strip()

        if old_pid:
            try:
                os.kill(int(old_pid), 0)
                logger.error(f"排程程式已在執行中 (PID={old_pid})，請先停止")
                sys.exit(1)
            except (ProcessLookupError, ValueError):
                os.remove(pid_file)


def write_pid(pid_file=PID_FILE):
    """寫入當前 PID。"""
    with open(pid_file, "w", encoding="utf-8") as file_obj:
        file_obj.write(str(os.getpid()))


def remove_pid(pid_file=PID_FILE):
    """移除 PID 檔案。"""
    if os.path.exists(pid_file):
        os.remove(pid_file)

