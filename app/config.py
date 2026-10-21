from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AIDASH_DATA_DIR", BASE_DIR / "data"))
STATIC_DIR = BASE_DIR / "static"

DB_PATH = DATA_DIR / "app.db"
SETTINGS_PATH = DATA_DIR / "settings.json"
KEY_PATH = Path(
    os.environ.get(
        "AIDASH_KEY_PATH",
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        / "ai-usage-dashboard"
        / "key",
    )
)

DEFAULT_SETTINGS: dict[str, Any] = {
    "auto_refresh_seconds": 300,
    "bill_month": "",  # 空表示使用当前账期
    "locale": "zh-CN",
    "minimax_base_url": "https://www.minimax.cn",
    "request_timeout_seconds": 20,
}


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict[str, Any]:
    ensure_dirs()
    settings = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        try:
            stored = json.loads(SETTINGS_PATH.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            stored = {}
        if isinstance(stored, dict):
            settings.update({k: v for k, v in stored.items() if k in DEFAULT_SETTINGS})
    return settings


def save_settings(updates: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    for key, value in updates.items():
        if key in DEFAULT_SETTINGS:
            settings[key] = value
    ensure_dirs()
    SETTINGS_PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    try:
        SETTINGS_PATH.chmod(0o600)
    except OSError:
        pass
    return settings
