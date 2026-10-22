"""传感器实体：每个账号一个，状态为主指标，细节放在属性里。"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LlmBalanceCoordinator
from .core.snapshot import Snapshot

# 内部单位 → Home Assistant 展示单位
UNIT_ALIASES = {
    "percent": "%",
    "credits": "Credits",
}


def _primary_metric(snapshot: Snapshot) -> dict[str, Any] | None:
    """优先取带进度（剩余额度）的指标，其次取第一个。"""
    for metric in snapshot.metrics:
        if metric.progress is not None:
            return metric.to_dict()
    return snapshot.metrics[0].to_dict() if snapshot.metrics else None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """建立该账号对应的传感器。"""
    coordinator: LlmBalanceCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LlmBalanceSensor(coordinator, entry)])


class LlmBalanceSensor(CoordinatorEntity[LlmBalanceCoordinator], SensorEntity):
    """单个账号的额度传感器。"""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: LlmBalanceCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{entry.data.get('account_id', entry.entry_id)}"
        self._attr_name = entry.data.get("label") or entry.data.get("platform")
        self._attr_icon = "mdi:chart-donut"

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def native_value(self) -> float | str | None:
        """数值型指标返回数字，带单位的显示交给 HA 渲染。"""
        snapshot = self.coordinator.data
        if snapshot is None:
            return None
        metric = _primary_metric(snapshot)
        if metric is None:
            return snapshot.status
        value = metric.get("value")
        if _is_number(value):
            return float(value)
        return metric.get("display")

    @property
    def native_unit_of_measurement(self) -> str | None:
        """仅在状态是数值时给出单位，否则 HA 会要求可转为 float。"""
        snapshot = self.coordinator.data
        if snapshot is None:
            return None
        metric = _primary_metric(snapshot)
        if metric is None or not _is_number(metric.get("value")):
            return None
        unit = metric.get("unit") or ""
        return UNIT_ALIASES.get(unit, unit) or None

    @property
    def state_class(self) -> SensorStateClass | None:
        """数值状态才声明 state_class，文本状态保持 None。"""
        return (
            SensorStateClass.MEASUREMENT
            if _is_number(self.native_value)
            else None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        snapshot = self.coordinator.data
        if snapshot is None:
            return {}
        metric = _primary_metric(snapshot)
        return {
            "platform": snapshot.platform,
            "mode": snapshot.mode,
            "status": snapshot.status,
            "error": snapshot.error,
            "fetched_at": snapshot.fetched_at,
            "latency_ms": snapshot.latency_ms,
            "metric": metric.get("label") if metric else None,
            "display": metric.get("display") if metric else None,
            "metrics": [metric.to_dict() for metric in snapshot.metrics],
            "breakdown": [item.to_dict() for item in snapshot.breakdown],
            "donut": snapshot.donut.to_dict() if snapshot.donut else None,
            "stacked": snapshot.stacked.to_dict() if snapshot.stacked else None,
            "notes": snapshot.notes,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
