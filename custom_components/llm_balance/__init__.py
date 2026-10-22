"""大模型额度看板（Home Assistant 集成）。

本模块刻意不在顶层导入 homeassistant，以便独立部署模式可以
直接复用 custom_components.llm_balance.core 下的实现。
"""

from __future__ import annotations

from datetime import timedelta
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
    from .settings import async_get_refresh_interval

    # 面板与 API 依赖 HTTP 组件；完整 HAOS 里它总是已加载，
    # 这里兜底保证在最小化安装（容器 / Core）下也能用。
    if hass.http is None:
        await async_setup_component(hass, "http", {})

    # 先注册视图与面板：即使首次取数失败，侧边栏入口也应当可用。
    await async_register_views(hass)
    await async_register_panel(hass)

    coordinator = LlmBalanceCoordinator(hass, entry)
    coordinator.update_interval = timedelta(
        seconds=await async_get_refresh_interval(hass)
    )
    # 不用 async_config_entry_first_refresh：网络抖动不应让整条配置项
    # 进入重试状态，传感器会以不可用态呈现，面板里能看到具体错误。
    await coordinator.async_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(coordinator.async_shutdown)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载单个账号。"""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded


def get_coordinators(hass: HomeAssistant) -> list[Any]:
    """返回全部账号的协调器。"""
    return list(hass.data.get(DOMAIN, {}).values())
