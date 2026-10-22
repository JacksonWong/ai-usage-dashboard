"""定时刷新单个账号的额度数据。"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, REFRESH_INTERVAL
from .core.models import Account
from .core.service import refresh_account
from .core.snapshot import Snapshot
from .settings import async_get_settings
from .store import ConfigEntryAccountStore

_LOGGER = logging.getLogger(__name__)


class LlmBalanceCoordinator(DataUpdateCoordinator[Snapshot]):
    """一个 config entry 对应一个账号，按固定间隔刷新。"""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self._store = ConfigEntryAccountStore(hass)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(20, connect=10.0),
            follow_redirects=False,
            headers={"User-Agent": "ai-usage-dashboard/0.1"},
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=REFRESH_INTERVAL),
        )

    @property
    def account(self) -> Account | None:
        entry = self.entry
        options = entry.options
        return Account(
            id=int(entry.data.get("account_id") or 0),
            platform=str(entry.data.get("platform") or ""),
            mode=str(entry.data.get("mode") or ""),
            label=str(entry.data.get("label") or entry.data.get("platform") or ""),
            credentials=dict(options.get("credentials") or {}),
            options=dict(options.get("options") or {}),
            enabled=bool(options.get("enabled", True)),
            created_at=entry.created_at,
            updated_at=entry.modified_at,
        )

    async def _async_update_data(self) -> Snapshot | None:
        account = self.account
        if account is None or not account.enabled:
            return None
        settings = await async_get_settings(self.hass)
        return await refresh_account(self._client, account, settings)

    async def async_shutdown(self) -> None:
        """释放 HTTP 客户端。"""
        await super().async_shutdown()
        await self._client.aclose()

    async def async_force_refresh(self) -> Snapshot | None:
        """忽略缓存强制抓取一次。"""
        await self.async_request_refresh()
        return self.data
