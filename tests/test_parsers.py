from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from custom_components.llm_balance.core.models import Account
from custom_components.llm_balance.core.providers.aliyun import AliyunProvider
from custom_components.llm_balance.core.providers.deepseek import DeepseekProvider
from custom_components.llm_balance.core.providers.minimax import MinimaxProvider

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text("utf-8"))


def account(
    platform: str,
    mode: str,
    label: str = "测试账号",
    **credentials: str,
) -> Account:
    return Account(
        id=1,
        platform=platform,
        mode=mode,
        label=label,
        credentials=credentials,
        options={},
    )


def client_with(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ------------------------------------------------------------------- 百炼


def aliyun_handler(request: httpx.Request) -> httpx.Response:
    action = request.headers.get("x-acs-action", "")
    host = request.url.host
    if host.startswith("business."):
        return httpx.Response(200, json=load("bss_balance.json"))
    if action == "GetBillingOverview":
        dimension = json.loads(dict(request.url.params).get("groupBy", "[]"))[0]["code"]
        payload = load("aliyun_billing_overview.json")
        if dimension == "BASE_MODEL":
            payload["data"]["groups"] = [
                {"key": "qwen-plus", "name": "qwen-plus", "amount": "20000", "percentage": "0.64"},
                {"key": "qwen-max", "name": "qwen-max", "amount": "10000", "percentage": "0.32"},
            ]
        else:
            payload["data"]["groups"] = [
                {"key": "sk-abc", "name": "sk-abc", "amount": "18000", "percentage": "0.58"},
                {"key": "sk-def", "name": "sk-def", "amount": "13228.60", "percentage": "0.42"},
            ]
        return httpx.Response(200, json=payload)
    if action == "GetBillingTrend":
        return httpx.Response(200, json=load("aliyun_billing_trend.json"))
    return httpx.Response(404, json={"Message": "unexpected action"})


async def test_aliyun_payg_snapshot():
    provider = AliyunProvider()
    acct = account("aliyun", "payg", access_key_id="AK", access_key_secret="SK")
    async with client_with(aliyun_handler) as client:
        snapshot = await provider.fetch(client, acct, {})

    assert snapshot.status == "ok"
    keys = {metric.key: metric for metric in snapshot.metrics}
    assert keys["month_billing"].value == 31228.60
    assert keys["month_billing"].display == "31,228.60 USD"
    assert keys["month_tax"].value == 2499.28
    assert keys["available_amount"].value == 10000.00
    assert keys["cash_balance"].value == 9000.00

    # 环形图：账单费用按模型拆分
    assert snapshot.donut is not None
    assert snapshot.donut.title == "账单费用 · 按 模型"
    assert snapshot.donut.total == 31228.60
    assert [item.name for item in snapshot.donut.items] == ["qwen-plus", "qwen-max"]
    assert snapshot.donut.items[0].value == 20000

    # 堆叠柱形图：按天 × 模型
    assert snapshot.stacked is not None
    assert snapshot.stacked.title == "账单趋势 · 按天 × 模型"
    assert snapshot.stacked.categories == ["qwen-plus"]
    assert len(snapshot.stacked.points) == 2
    assert snapshot.stacked.points[0].label == "08-01"
    assert snapshot.stacked.points[0].total == 30
    assert snapshot.stacked.points[0].parts[0].name == "qwen-plus"
    assert snapshot.stacked.points[0].parts[0].value == 20

    # 筛选条件
    assert snapshot.filters["bill_month"]["value"] == snapshot.filters["bill_month"]["value"]
    assert snapshot.filters["dimension"]["value"] == "BASE_MODEL"
    assert [o["value"] for o in snapshot.filters["dimension"]["options"]] == [
        "BASE_MODEL",
        "API_KEY_ID",
    ]


async def test_aliyun_payg_api_key_dimension():
    provider = AliyunProvider()
    acct = account("aliyun", "payg", access_key_id="AK", access_key_secret="SK")
    acct.options = {"dimension": "API_KEY_ID"}
    async with client_with(aliyun_handler) as client:
        snapshot = await provider.fetch(client, acct, {})

    assert snapshot.filters["dimension"]["value"] == "API_KEY_ID"
    assert snapshot.donut.title == "账单费用 · 按 API Key"
    assert [item.name for item in snapshot.donut.items] == ["sk-abc", "sk-def"]
    assert snapshot.stacked.title == "账单趋势 · 按天 × API Key"


async def test_aliyun_payg_uses_requested_bill_month():
    provider = AliyunProvider()
    acct = account("aliyun", "payg", access_key_id="AK", access_key_secret="SK")
    acct.options = {"bill_month": "2026-08"}
    async with client_with(aliyun_handler) as client:
        snapshot = await provider.fetch(client, acct, {})

    assert snapshot.filters["bill_month"]["value"] == "2026-08"
    billing = next(m for m in snapshot.metrics if m.key == "month_billing")
    assert billing.label == "2026-08 账单费用"


async def test_aliyun_payg_degrades_when_balance_denied():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host.startswith("business."):
            return httpx.Response(
                400,
                json={
                    "Code": "NoPermission",
                    "Message": "You are not authorized to perform this action.",
                },
            )
        return aliyun_handler(request)

    provider = AliyunProvider()
    acct = account("aliyun", "payg", access_key_id="AK", access_key_secret="SK")
    async with client_with(handler) as client:
        snapshot = await provider.fetch(client, acct, {})

    assert snapshot.status == "ok"
    assert any("bss:DescribeAcccount" in note for note in snapshot.notes)
    assert not any(metric.key == "available_amount" for metric in snapshot.metrics)


async def test_aliyun_payg_error_when_core_call_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"Code": "InvalidParameter", "Message": "bad param"})

    provider = AliyunProvider()
    acct = account("aliyun", "payg", access_key_id="AK", access_key_secret="SK")
    async with client_with(handler) as client:
        snapshot = await provider.fetch(client, acct, {})

    assert snapshot.status == "error"
    assert "bad param" in (snapshot.error or "")


async def test_aliyun_token_plan_snapshot():
    def handler(request: httpx.Request) -> httpx.Response:
        action = request.headers.get("x-acs-action", "")
        if action == "GetSubscriptionStats":
            return httpx.Response(200, json=load("aliyun_subscription_stats.json"))
        if action == "GetSubscriptionSeatDetails":
            return httpx.Response(200, json=load("aliyun_seat_detail.json"))
        if action == "ListSubscriptionSharedPackages":
            return httpx.Response(200, json=load("aliyun_shared_packages.json"))
        return httpx.Response(404, json={"Message": "unexpected"})

    provider = AliyunProvider()
    acct = account("aliyun", "token_plan", access_key_id="AK", access_key_secret="SK")
    async with client_with(handler) as client:
        snapshot = await provider.fetch(client, acct, {})

    assert snapshot.status == "ok"
    keys = {metric.key: metric for metric in snapshot.metrics}
    assert keys["remaining_credits"].value == 40
    assert keys["remaining_credits"].total == 100
    assert keys["remaining_credits"].progress == pytest.approx(0.4)
    assert keys["used_credits"].value == 60
    assert keys["seats"].display == "1 / 2"
    assert "subscription_end" in keys

    dimensions = {item.dimension for item in snapshot.breakdown}
    assert {"席位档位", "席位明细", "共享包"} <= dimensions


# ------------------------------------------------------------------ MiniMax


async def test_minimax_adaptive_parsing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=load("minimax_remains.json"))

    provider = MinimaxProvider()
    acct = account("minimax", "token_plan", api_key="sk-mm")
    async with client_with(handler) as client:
        snapshot = await provider.fetch(client, acct, {})

    assert snapshot.status == "ok"
    labels = {metric.label for metric in snapshot.metrics}
    assert "plan remaining credits" in labels
    assert "plan total credits" in labels

    remaining = next(m for m in snapshot.metrics if m.label == "plan remaining credits")
    assert remaining.value == 620
    assert remaining.total == 1000
    assert remaining.progress == pytest.approx(0.62)

    assert snapshot.notes
    assert snapshot.raw == load("minimax_remains.json")


async def test_minimax_model_remains_shape():
    """官方未公开但结构稳定的 model_remains 响应，按窗口解析。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=load("minimax_model_remains.json"))

    provider = MinimaxProvider()
    acct = account("minimax", "token_plan", api_key="sk-mm")
    async with client_with(handler) as client:
        snapshot = await provider.fetch(client, acct, {})

    assert snapshot.status == "ok"
    by_key = {m.key: m for m in snapshot.metrics}

    general = by_key["interval_remaining:general"]
    assert general.label == "通用模型 · 5 小时窗口"
    assert general.display == "93.0%"
    assert general.progress == pytest.approx(0.93)
    assert general.total == 20
    assert "已用 1 / 20" in general.hint
    assert "后重置" in general.hint
    assert "至 " in general.hint

    weekly = by_key["weekly_remaining:general"]
    assert weekly.display == "64.0%"
    assert weekly.total == 100
    assert "已用 36 / 100" in weekly.hint

    video = by_key["interval_remaining:video"]
    assert video.label == "视频模型 · 5 小时窗口"
    assert video.display == "100.0%"

    assert len(snapshot.metrics) == 4
    assert snapshot.breakdown == []


async def test_minimax_error_envelope():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=load("minimax_error.json"))

    provider = MinimaxProvider()
    acct = account("minimax", "token_plan", api_key="sk-mm")
    async with client_with(handler) as client:
        snapshot = await provider.fetch(client, acct, {})

    assert snapshot.status == "error"
    assert "login fail" in (snapshot.error or "")


async def test_minimax_unknown_shape_still_returns_raw():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"base_resp": {"status_code": 0}, "weird": {"a": 1}})

    provider = MinimaxProvider()
    acct = account("minimax", "token_plan", api_key="sk-mm")
    async with client_with(handler) as client:
        snapshot = await provider.fetch(client, acct, {})

    assert snapshot.status == "ok"
    assert snapshot.raw == {"base_resp": {"status_code": 0}, "weird": {"a": 1}}


# ----------------------------------------------------------------- DeepSeek


async def test_deepseek_balance():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer sk-ds"
        if request.url.path == "/models":
            return httpx.Response(200, json=load("deepseek_models.json"))
        return httpx.Response(200, json=load("deepseek_balance.json"))

    provider = DeepseekProvider()
    acct = account("deepseek", "payg", api_key="sk-ds")
    async with client_with(handler) as client:
        snapshot = await provider.fetch(client, acct, {})

    assert snapshot.status == "ok"
    keys = {metric.key: metric for metric in snapshot.metrics}
    assert keys["total_balance"].value == 110.00
    assert keys["total_balance"].display == "110.00 CNY"
    assert keys["granted_balance"].value == 10.00
    assert keys["topped_up_balance"].value == 100.00
    assert snapshot.breakdown == []
    assert [model.id for model in snapshot.models] == ["deepseek-chat", "deepseek-reasoner"]
    assert snapshot.models[0].name == "DeepSeek-V3.2-Exp"
    assert snapshot.models[0].context_window == 131072
    assert snapshot.models[0].max_output_tokens == 8192
    assert snapshot.models[0].input_modalities == ["text"]
    assert snapshot.notes == []
    assert set(snapshot.raw) == {"user_balance", "models"}
    assert snapshot.raw["models"]["object"] == "list"


async def test_deepseek_models_failure_degrades():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/models":
            return httpx.Response(500, json={"error": {"message": "boom"}})
        return httpx.Response(200, json=load("deepseek_balance.json"))

    provider = DeepseekProvider()
    acct = account("deepseek", "payg", api_key="sk-ds")
    async with client_with(handler) as client:
        snapshot = await provider.fetch(client, acct, {})

    assert snapshot.status == "ok"
    assert {metric.key for metric in snapshot.metrics} >= {"total_balance"}
    assert snapshot.models == []
    assert any("模型列表获取失败" in note for note in snapshot.notes)


async def test_deepseek_unavailable_account():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"is_available": False, "balance_infos": []})

    provider = DeepseekProvider()
    acct = account("deepseek", "payg", api_key="sk-ds")
    async with client_with(handler) as client:
        snapshot = await provider.fetch(client, acct, {})

    assert snapshot.status == "error"
    assert "is_available" in (snapshot.error or "")
