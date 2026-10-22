"""Home Assistant 原生配置流。

表单结构由 core.models.PLATFORM_SPECS 驱动，与独立部署模式的账号表单保持一致。
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import DOMAIN
from .core.models import PLATFORM_SPECS, missing_credentials


def _platform_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("platform"): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=spec.key, label=spec.label)
                        for spec in PLATFORM_SPECS.values()
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        }
    )


def _mode_schema(platform: str) -> vol.Schema:
    spec = PLATFORM_SPECS[platform]
    return vol.Schema(
        {
            vol.Required("mode"): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=mode.key, label=mode.label)
                        for mode in spec.modes
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        }
    )


def _credentials_schema(platform: str, mode: str) -> vol.Schema:
    spec = PLATFORM_SPECS[platform]
    mode_spec = spec.mode(mode)
    schema: dict[Any, Any] = {
        vol.Required("label", default=spec.short): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        )
    }
    for field in mode_spec.fields if mode_spec else ():
        schema[
            vol.Required(field.name, default=field.default)
            if field.required
            else vol.Optional(field.name, default=field.default)
        ] = TextSelector(
            TextSelectorConfig(
                type=(
                    TextSelectorType.PASSWORD
                    if field.secret
                    else TextSelectorType.TEXT
                )
            )
        )
    return vol.Schema(schema)


class LlmBalanceConfigFlow(ConfigFlow, domain=DOMAIN):
    """添加一个接入账号。"""

    VERSION = 1

    def __init__(self) -> None:
        self._platform: str = ""
        self._mode: str = ""
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._platform = user_input["platform"]
            return await self.async_step_mode()
        return self.async_show_form(step_id="user", data_schema=_platform_schema())

    async def async_step_mode(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._mode = user_input["mode"]
            return await self.async_step_credentials()
        return self.async_show_form(
            step_id="mode", data_schema=_mode_schema(self._platform)
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ):
        errors: dict[str, str] = {}
        mode_spec = PLATFORM_SPECS[self._platform].mode(self._mode)
        field_names = [f.name for f in mode_spec.fields] if mode_spec else []

        if user_input is not None:
            label = str(user_input.get("label") or PLATFORM_SPECS[self._platform].short)
            credentials = {
                name: str(user_input.get(name) or "").strip()
                for name in field_names
                if user_input.get(name)
            }
            missing = missing_credentials(self._platform, self._mode, credentials)
            if missing:
                errors["base"] = "missing_credentials"
            else:
                await self.async_set_unique_id(
                    f"{self._platform}_{self._mode}_{label}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=label,
                    data={
                        "platform": self._platform,
                        "mode": self._mode,
                        "label": label,
                    },
                    options={
                        "credentials": credentials,
                        "options": {},
                        "enabled": True,
                    },
                )

        return self.async_show_form(
            step_id="credentials",
            data_schema=_credentials_schema(self._platform, self._mode),
            errors=errors,
            description_placeholders={
                "docs": " ".join(mode_spec.docs) if mode_spec else "",
            },
        )

    async def async_step_import(self, user_input: dict[str, Any]):
        """内部导入（由面板 API 调用），直接建条目。"""
        data = dict(user_input)
        credentials = data.pop("credentials", {}) or {}
        options = data.pop("options", {}) or {}
        enabled = data.pop("enabled", True)
        account_id = data.pop("account_id", 0)
        platform = data["platform"]
        mode = data["mode"]
        label = data["label"]

        await self.async_set_unique_id(f"{platform}_{mode}_{label}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=label,
            data={
                "account_id": account_id,
                "platform": platform,
                "mode": mode,
                "label": label,
            },
            options={
                "credentials": credentials,
                "options": options,
                "enabled": enabled,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        # 2025.1+ 由框架把 config entry 关联到 flow（self.handler），
        # 不要再往构造函数传参（2025.12 起手动设置 config_entry 会报错）。
        return LlmBalanceOptionsFlow()


class LlmBalanceOptionsFlow(config_entries.OptionsFlow):
    """编辑已有账号的备注与筛选条件。"""

    @property
    def _entry(self) -> ConfigEntry:
        """取当前配置项：优先用基类提供的，2024.10 则按 handler 查。"""
        try:
            entry = self.config_entry
        except (AttributeError, ValueError):
            entry = None
        if entry is not None:
            return entry
        return self.hass.config_entries.async_get_known_entry(self.handler)

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        entry = self._entry
        if user_input is not None:
            data = dict(entry.data)
            if user_input.get("label"):
                data["label"] = user_input["label"]
            # 选项流的 data 会整体替换 entry.options，必须回传完整内容，
            # 否则凭据等字段会被清空。
            new_options = dict(entry.options)
            self.hass.config_entries.async_update_entry(
                entry, data=data, options=new_options
            )
            return self.async_create_entry(title="", data=new_options)

        # 统计维度与账期是面板里的实时筛选项，不属于配置项
        schema: dict[Any, Any] = {
            vol.Required(
                "label", default=entry.data.get("label", "")
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))
        }
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
