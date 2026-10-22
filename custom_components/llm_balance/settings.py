"""全局设置（Home Assistant 侧用 Store 持久化）。"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, REFRESH_INTERVAL

STORAGE_KEY = f"{DOMAIN}.settings"
STORAGE_VERSION = 1
_STORE_KEY = f"{DOMAIN}.settings_store"

DEFAULT_SETTINGS: dict[str, Any] = {
    "auto_refresh_seconds": REFRESH_INTERVAL,
    "bill_month": "",
    "locale": "zh-CN",
    "minimax_base_url": "https://www.minimax.cn",
    "request_timeout_seconds": 20,
}


def _store(hass: HomeAssistant) -> Store:
    """复用同一个 Store 实例，避免每次调用都新建。"""
    store = hass.data.get(_STORE_KEY)
    if store is None:
        store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        hass.data[_STORE_KEY] = store
    return store


async def async_get_settings(hass: HomeAssistant) -> dict[str, Any]:
    data = await _store(hass).async_load()
    settings = dict(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        settings.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
    return settings


async def async_get_refresh_interval(hass: HomeAssistant) -> int:
    settings = await async_get_settings(hass)
    interval = int(settings.get("auto_refresh_seconds") or 0)
    return interval if interval > 0 else REFRESH_INTERVAL


async def async_save_settings(
    hass: HomeAssistant, updates: dict[str, Any]
) -> dict[str, Any]:
    current = await async_get_settings(hass)
    current.update({k: v for k, v in updates.items() if k in DEFAULT_SETTINGS})
    await _store(hass).async_save(current)
    return current
