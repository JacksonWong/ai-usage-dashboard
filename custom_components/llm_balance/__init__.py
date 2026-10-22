"""大模型额度看板（Home Assistant 集成）。

本模块刻意不在顶层导入 homeassistant，以便独立部署模式可以
直接复用 custom_components.llm_balance.core 下的实现。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """建立单个账号的协调器。"""
    from homeassistant.setup import async_setup_component

    from .coordinator import LlmBalanceCoordinator
    from .panel import async_register_panel, async_register_views

    # 面板与 API 依赖 HTTP 组件；完整 HAOS 里它总是已加载，
    # 这里兜底保证在最小化安装（容器 / Core）下也能用。
    if hass.http is None:
        await async_setup_component(hass, "http", {})

    await async_register_views(hass)
    coordinator = LlmBalanceCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await async_register_panel(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载单个账号。"""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """配置项变更后重载。"""
    await hass.config_entries.async_reload(entry.entry_id)


def get_coordinators(hass: HomeAssistant) -> list[Any]:
    """返回全部账号的协调器。"""
    return list(hass.data.get(DOMAIN, {}).values())
