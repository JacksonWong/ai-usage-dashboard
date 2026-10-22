"""Home Assistant 侧的账号存储：以 config entry 为准。

每个接入账号对应一个 config entry：
- entry.data    : account_id / platform / mode / label
- entry.options : credentials / options / enabled
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .core.models import Account


class ConfigEntryAccountStore:
    """把 HA 的 config entry 适配成统一的异步账号存储接口。"""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def _entries(self) -> list[ConfigEntry]:
        return list(self.hass.config_entries.async_entries(DOMAIN))

    def _to_account(self, entry: ConfigEntry) -> Account:
        data = entry.data
        options = entry.options
        return Account(
            id=int(data.get("account_id") or 0),
            platform=str(data.get("platform") or ""),
            mode=str(data.get("mode") or ""),
            label=str(data.get("label") or data.get("platform") or ""),
            credentials=dict(options.get("credentials") or {}),
            options=dict(options.get("options") or {}),
            enabled=bool(options.get("enabled", True)),
            created_at=entry.created_at,
            updated_at=entry.modified_at,
        )

    def _entry_for(self, account_id: int) -> ConfigEntry | None:
        for entry in self._entries():
            if int(entry.data.get("account_id") or 0) == account_id:
                return entry
        return None

    def next_account_id(self) -> int:
        used = [int(entry.data.get("account_id") or 0) for entry in self._entries()]
        return (max(used) + 1) if used else 1

    async def list_accounts(self) -> list[Account]:
        return [self._to_account(entry) for entry in self._entries()]

    async def get_account(self, account_id: int) -> Account | None:
        entry = self._entry_for(account_id)
        return self._to_account(entry) if entry else None

    async def create_account(
        self,
        platform: str,
        mode: str,
        label: str,
        credentials: dict[str, str],
        options: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> Account:
        """通过内部导入流程创建一个账号。"""
        result = await self.hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={
                "account_id": self.next_account_id(),
                "platform": platform,
                "mode": mode,
                "label": label,
                "credentials": credentials,
                "options": options or {},
                "enabled": enabled,
            },
        )
        entry = self.hass.config_entries.async_get_entry(result["result"]["entry_id"])
        return self._to_account(entry)

    async def update_account(
        self,
        account_id: int,
        *,
        label: str | None = None,
        mode: str | None = None,
        credentials: dict[str, str] | None = None,
        options: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> Account | None:
        entry = self._entry_for(account_id)
        if entry is None:
            return None

        data = dict(entry.data)
        if label is not None:
            data["label"] = label
        if mode is not None:
            data["mode"] = mode

        merged_options = dict(entry.options)
        if credentials:
            merged = dict(merged_options.get("credentials") or {})
            merged.update({k: v for k, v in credentials.items() if v})
            merged_options["credentials"] = merged
        if options is not None:
            merged = dict(merged_options.get("options") or {})
            merged.update(options)
            merged_options["options"] = merged
        if enabled is not None:
            merged_options["enabled"] = enabled

        self.hass.config_entries.async_update_entry(
            entry, data=data, options=merged_options
        )
        return self._to_account(entry)

    async def delete_account(self, account_id: int) -> bool:
        entry = self._entry_for(account_id)
        if entry is None:
            return False
        await self.hass.config_entries.async_remove(entry.entry_id)
        return True
