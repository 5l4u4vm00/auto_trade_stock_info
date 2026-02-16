"""排程啟動設定載入。"""

import logging
import os
import sys

try:
    from config_loader import load_yaml_config
except ModuleNotFoundError:  # pragma: no cover
    from scheduler.config_loader import load_yaml_config  # type: ignore

SCHEDULER_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.abspath(os.path.join(SCHEDULER_DIR, "..", "config.yaml"))

logger = logging.getLogger("scheduler")


def load_config(config_file=CONFIG_FILE):
    """讀取 config.yaml。"""
    # 2026-02-15 調整方式: 從 main.py 抽離設定讀取與檢查，保留相同行為。
    if not os.path.exists(config_file):
        logger.error(f"設定檔不存在: {config_file}")
        sys.exit(1)

    config = load_yaml_config(config_file)
    email_cfg = config.get("email", {})
    required_fields = ["smtp_host", "smtp_port", "sender", "password", "recipient"]
    missing_fields = [field for field in required_fields if not email_cfg.get(field)]
    if missing_fields:
        logger.warning(f"email 設定缺少欄位: {missing_fields}")
    return config

