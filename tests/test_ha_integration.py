"""Home Assistant 集成运行时测试。

需要额外依赖（不在默认依赖里）：
    uv pip install pytest-homeassistant-custom-component==0.13.199
未安装时整组跳过。
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip(
    "pytest_homeassistant_custom_component",
    reason="需要 pytest-homeassistant-custom-component",
)

from homeassistant.helpers import entity_registry as er  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
)

from custom_components.llm_balance.const import DOMAIN  # noqa: E402
from custom_components.llm_balance.core.snapshot import (  # noqa: E402
    Metric,
    Snapshot,
)

ACCOUNT = {
    "account_id": 1,
    "platform": "aliyun",
    "mode": "payg",
    "label": "测试账号",
}
OPTIONS = {
    "credentials": {"access_key_id": "LTAI-fake", "access_key_secret": "fake"},
    "options": {"dimension": "BASE_MODEL"},
    "enabled": True,
}


@pytest.fixture(autouse=True)
def auto_enable(enable_custom_integrations):
    yield


async def test_setup_creates_sensor_and_panel(hass):
    """配置项建立后应生成传感器并注册侧边栏面板。"""
    entry = MockConfigEntry(domain=DOMAIN, data=ACCOUNT, options=OPTIONS)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator is not None

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DOMAIN}_{ACCOUNT['account_id']}"
    )
    assert entity_id is not None, "未创建传感器实体"
    state = hass.states.get(entity_id)
    assert state.attributes["platform"] == "aliyun"
    assert state.attributes["mode"] == "payg"

    panels = hass.data.get("frontend_panels", {})
    assert panels.get(f"/{DOMAIN}"), "侧边栏面板未注册"


async def test_dashboard_api(hass, hass_client):
    """面板的 JSON API 应可访问并返回汇总。"""
    entry = MockConfigEntry(domain=DOMAIN, data=ACCOUNT, options=OPTIONS)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    client = await hass_client()
    response = await client.get(f"/api/{DOMAIN}/dashboard")
    assert response.status == 200
    payload = await response.json()
    assert payload["summary"]["total"] == 1
    assert payload["items"][0]["platform"] == "aliyun"
    # 测试环境禁外网，快照可能是 error 态；成功时才带筛选条件
    if payload["items"][0]["status"] == "ok":
        assert payload["items"][0]["filters"]["dimension"]["value"] == "BASE_MODEL"

    response = await client.get(f"/api/{DOMAIN}/accounts")
    assert response.status == 200
    accounts = await response.json()
    assert accounts["items"][0]["label"] == "测试账号"
    assert "LTAI-fake" not in str(accounts), "掩码失效：明文密钥外泄"


async def test_config_flow(hass):
    """原生配置流应能走完并创建配置项。"""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"platform": "aliyun"}
    )
    assert result["step_id"] == "mode"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"mode": "payg"}
    )
    assert result["step_id"] == "credentials"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "label": "流创建的账号",
            "access_key_id": "LTAI-fake",
            "access_key_secret": "fake",
            "region_id": "cn-beijing",
        },
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "流创建的账号"
    assert result["data"]["platform"] == "aliyun"
    assert result["options"]["credentials"]["access_key_id"] == "LTAI-fake"


async def test_config_flow_rejects_missing_credentials(hass):
    """缺少必填凭据时应报错而不是建条目。"""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"platform": "minimax"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"mode": "token_plan"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"label": "缺 key", "api_key": ""}
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "missing_credentials"}


async def _setup_with_snapshot(hass, snapshot: Snapshot) -> str:
    """建立集成并用给定快照覆盖协调器数据，返回实体 id。"""
    entry = MockConfigEntry(domain=DOMAIN, data=ACCOUNT, options=OPTIONS)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.data = snapshot
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    return registry.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_1")


async def test_sensor_state_is_numeric_when_unit_present(hass):
    """有单位时状态必须是数值，否则 HA 会 float() 转换失败。"""
    entity_id = await _setup_with_snapshot(
        hass,
        Snapshot(
            account_id=1,
            platform="aliyun",
            mode="payg",
            label="测试账号",
            metrics=[
                Metric(
                    key="available_amount",
                    label="账户可用额度",
                    value=7.76,
                    display="7.76 CNY",
                    unit="CNY",
                )
            ],
        ),
    )
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "7.76", "状态必须是纯数值"
    assert float(state.state) == 7.76
    assert state.attributes["unit_of_measurement"] == "CNY"
    assert state.attributes["display"] == "7.76 CNY"
    assert state.attributes["state_class"] == "measurement"


async def test_sensor_state_is_text_when_no_numeric_value(hass):
    """指标没有数值时状态退化为文本，且不带单位。"""
    entity_id = await _setup_with_snapshot(
        hass,
        Snapshot(
            account_id=1,
            platform="aliyun",
            mode="token_plan",
            label="测试账号",
            metrics=[
                Metric(
                    key="subscription_end",
                    label="订阅到期",
                    value=None,
                    display="2026-11-19 14:00",
                    unit="",
                )
            ],
        ),
    )
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "2026-11-19 14:00"
    assert state.attributes.get("unit_of_measurement") is None


async def test_multiple_entries_do_not_race_on_panel(hass, caplog):
    """多个账号并发 setup 时，侧边栏面板只能注册一次。"""
    entries = []
    for index in range(3):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={**ACCOUNT, "account_id": index + 1, "label": f"账号{index + 1}"},
            options=OPTIONS,
        )
        entry.add_to_hass(hass)
        entries.append(entry)

    await asyncio.gather(
        *(hass.config_entries.async_setup(entry.entry_id) for entry in entries)
    )
    await hass.async_block_till_done()

    assert "Overwriting panel" not in caplog.text
    panels = hass.data.get("frontend_panels", {})
    assert panels.get(f"/{DOMAIN}"), "侧边栏面板未注册"
    for entry in entries:
        assert hass.states.get(
            er.async_get(hass).async_get_entity_id(
                "sensor", DOMAIN, f"{DOMAIN}_{entry.data['account_id']}"
            )
        )


async def test_options_flow_can_be_opened(hass):
    """配置项的选项流应能正常打开（2025.1+ 不再向构造函数传参）。"""
    entry = MockConfigEntry(domain=DOMAIN, data=ACCOUNT, options=OPTIONS)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"label": "改过的名字", "dimension": "API_KEY_ID"}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["options"]["dimension"] == "API_KEY_ID"
    assert entry.data["label"] == "改过的名字"
    # 选项流的 data 会整体替换 options，凭据不能被清空
    assert entry.options["credentials"]["access_key_id"] == "LTAI-fake"
