from __future__ import annotations

import json


def test_health_and_platforms(client):
    assert client.get("/api/health").json() == {"status": "ok"}

    payload = client.get("/api/platforms").json()
    keys = {item["key"] for item in payload["items"]}
    assert keys == {"aliyun", "minimax", "deepseek"}

    aliyun = next(item for item in payload["items"] if item["key"] == "aliyun")
    assert {mode["key"] for mode in aliyun["modes"]} == {"payg", "token_plan"}

    minimax = next(item for item in payload["items"] if item["key"] == "minimax")
    assert [mode["key"] for mode in minimax["modes"]] == ["token_plan"]

    deepseek = next(item for item in payload["items"] if item["key"] == "deepseek")
    assert [mode["key"] for mode in deepseek["modes"]] == ["payg"]


def test_create_account_requires_credentials(client):
    response = client.post(
        "/api/accounts",
        json={
            "platform": "aliyun",
            "mode": "payg",
            "label": "缺少凭据",
            "credentials": {},
        },
    )
    assert response.status_code == 400
    assert "access_key_id" in response.json()["detail"]


def test_create_account_rejects_unknown_mode(client):
    response = client.post(
        "/api/accounts",
        json={
            "platform": "deepseek",
            "mode": "token_plan",
            "label": "非法模式",
            "credentials": {"api_key": "sk-x"},
        },
    )
    assert response.status_code == 400
    assert "不支持该模式" in response.json()["detail"]


def test_account_crud_masks_secrets(client):
    created = client.post(
        "/api/accounts",
        json={
            "platform": "deepseek",
            "mode": "payg",
            "label": "主账号",
            "credentials": {"api_key": "sk-abcdef123456"},
        },
    )
    assert created.status_code == 201
    body = created.json()
    account_id = body["id"]
    assert body["credential_mask"]["api_key"].startswith("sk-a")
    assert "sk-abcdef123456" not in created.text

    listed = client.get("/api/accounts").json()
    assert len(listed["items"]) == 1
    assert "sk-abcdef123456" not in json.dumps(listed)

    updated = client.put(
        f"/api/accounts/{account_id}",
        json={"label": "主账号-改名", "credentials": {"api_key": "sk-zzzz999888"}},
    )
    assert updated.status_code == 200
    assert updated.json()["label"] == "主账号-改名"
    assert "sk-zzzz999888" not in updated.text

    deleted = client.delete(f"/api/accounts/{account_id}")
    assert deleted.status_code == 200
    assert client.get("/api/accounts").json()["items"] == []


def test_update_keeps_existing_secret_when_blank(client):
    created = client.post(
        "/api/accounts",
        json={
            "platform": "minimax",
            "mode": "token_plan",
            "label": "M Plan",
            "credentials": {"api_key": "eyJhbGciOiAAAA"},
        },
    ).json()

    updated = client.put(
        f"/api/accounts/{created['id']}",
        json={"credentials": {"api_key": ""}, "label": "改名"},
    )
    assert updated.status_code == 200
    assert updated.json()["label"] == "改名"
    assert updated.json()["credential_mask"]["api_key"].startswith("eyJh")


def test_dashboard_returns_summary(client):
    client.post(
        "/api/accounts",
        json={
            "platform": "deepseek",
            "mode": "payg",
            "label": "主账号",
            "credentials": {"api_key": "sk-invalid"},
        },
    )
    payload = client.get("/api/dashboard").json()
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["failed"] == 1
    assert payload["items"][0]["status"] == "error"
    assert "sk-invalid" not in json.dumps(payload)

    # 第二次命中缓存路径（曾因时区感知/朴素时间比较导致 500）
    cached = client.get("/api/dashboard").json()
    assert cached["summary"]["total"] == 1
    assert client.get("/api/dashboard?refresh=1").status_code == 200


def test_dashboard_sums_spend_from_successful_account(client, monkeypatch):
    """成功返回的账号必须能正常聚合（曾因 dict/属性混用导致 500）。"""
    from app.providers.aliyun import AliyunProvider
    from app.snapshot import BreakdownItem, Metric, SeriesPoint, Snapshot

    async def fake_fetch(self, client, account, settings):
        return Snapshot(
            account_id=account.id,
            platform=account.platform,
            mode=account.mode,
            label=account.label,
            fetched_at="2026-10-21T02:40:49+00:00",
            latency_ms=120,
            metrics=[
                Metric(
                    key="month_total",
                    label="2026-10 消费合计",
                    value=3128.6,
                    display="3,128.60 USD",
                    unit="USD",
                ),
                Metric(key="available_amount", label="账户可用额度", value=100.0, display="100.00 CNY"),
            ],
            breakdown=[
                BreakdownItem(name="qwen-plus", value=10.0, display="10.00 USD", percentage=0.5)
            ],
            series=[SeriesPoint(label="10-01", value=1.0, display="1.00 USD")],
            raw={"data": {}},
        )

    monkeypatch.setattr(AliyunProvider, "fetch", fake_fetch)

    created = client.post(
        "/api/accounts",
        json={
            "platform": "aliyun",
            "mode": "payg",
            "label": "可用账号",
            "credentials": {"access_key_id": "AK", "access_key_secret": "SK"},
        },
    )
    assert created.status_code == 201

    response = client.get("/api/dashboard?refresh=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["ok"] == 1
    assert payload["summary"]["failed"] == 0
    assert payload["items"][0]["metrics"][0]["key"] == "month_total"
    assert payload["items"][0]["metrics"][0]["value"] == 3128.6
    assert payload["items"][0]["breakdown"][0]["name"] == "qwen-plus"


def test_settings_roundtrip(client):
    original = client.get("/api/settings").json()
    assert "auto_refresh_seconds" in original

    updated = client.put(
        "/api/settings", json={"auto_refresh_seconds": 60, "locale": "en-US"}
    ).json()
    assert updated["auto_refresh_seconds"] == 60
    assert updated["locale"] == "en-US"
    assert client.get("/api/settings").json()["auto_refresh_seconds"] == 60


def test_settings_validation(client):
    assert client.put("/api/settings", json={"locale": "fr-FR"}).status_code == 400
    assert client.put("/api/settings", json={"bill_month": "2026"}).status_code == 400
    assert (
        client.put("/api/settings", json={"minimax_base_url": "http://x"}).status_code
        == 400
    )


def test_security_headers_present(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in response.headers
