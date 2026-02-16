"""設定檔載入模組。"""

import os
import re
from pathlib import Path

import yaml

ENV_TOKEN_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}")


def _resolve_env_tokens(raw_text):
    """將字串中的 ${ENV} / ${ENV:default} 轉為實際值。"""

    def _replace(match_obj):
        env_name = match_obj.group(1)
        default_value = match_obj.group(2)
        env_value = os.getenv(env_name)
        if env_value is not None:
            return env_value
        return default_value if default_value is not None else ""

    if not isinstance(raw_text, str):
        return raw_text
    return ENV_TOKEN_PATTERN.sub(_replace, raw_text)


def _resolve_payload(payload):
    if isinstance(payload, dict):
        return {key: _resolve_payload(value) for key, value in payload.items()}

    if isinstance(payload, list):
        return [_resolve_payload(item) for item in payload]

    if isinstance(payload, str):
        return _resolve_env_tokens(payload)

    return payload


def load_yaml_config(config_path):
    """讀取 YAML 設定檔並套用環境變數。"""
    # 2026-02-15 調整方式: 支援 ${ENV} 與 ${ENV:default}，避免機敏資訊寫死在 repo。
    path_obj = Path(config_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"設定檔不存在: {config_path}")

    with path_obj.open("r", encoding="utf-8") as file_obj:
        payload = yaml.safe_load(file_obj)

    if payload is None:
        payload = {}

    return _resolve_payload(payload)
