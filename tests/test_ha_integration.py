"""Home Assistant 集成运行时测试。

需要额外依赖（不在默认依赖里）：
    uv pip install pytest-homeassistant-custom-component==0.13.199
未安装时整组跳过。
"""

from __future__ import annotations

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
