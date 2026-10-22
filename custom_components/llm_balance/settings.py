"""全局设置（Home Assistant 侧用 Store 持久化）。"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, REFRESH_INTERVAL

STORAGE_KEY = f"{DOMAIN}.settings"
STORAGE_VERSION = 1

DEFAULT_SETTINGS: dict[str, Any] = {
    "auto_refresh_seconds": REFRESH_INTERVAL,
    "bill_month": "",
    "locale": "zh-CN",
    "minimax_base_url": "https://www.minimax.cn",
    "request_timeout_seconds": 20,
}


async def async_get_settings(hass: HomeAssistant) -> dict[str, Any]:
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    data = await store.async_load()
    settings = dict(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        settings.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
    return settings


async def async_save_settings(
    hass: HomeAssistant, updates: dict[str, Any]
) -> dict[str, Any]:
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    current = await async_get_settings(hass)
    current.update({k: v for k, v in updates.items() if k in DEFAULT_SETTINGS})
    await store.async_save(current)
    return current
