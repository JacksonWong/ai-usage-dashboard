"""侧边栏面板与 JSON API。

面板通过 homeassistant.components.panel_custom 注册到 HA 侧边栏，
前端资源与独立部署模式共用同一份 www 目录。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.http import KEY_HASS

from .const import DOMAIN, PANEL_ICON, PANEL_TITLE, PANEL_URL_PATH, STATIC_URL
from .core.models import (
    PLATFORM_SPECS,
    missing_credentials,
    platform_specs_payload,
    validate_options,
    validate_target,
)
from .settings import async_get_settings, async_save_settings
from .store import ConfigEntryAccountStore

_LOGGER = logging.getLogger(__name__)

WWW_DIR = Path(__file__).parent / "www"

_PANEL_REGISTERED = f"{DOMAIN}_panel_registered"


def _store(hass: HomeAssistant) -> ConfigEntryAccountStore:
    return ConfigEntryAccountStore(hass)


def _coordinators(hass: HomeAssistant):
    from . import get_coordinators

    return get_coordinators(hass)


async def async_register_panel(hass: HomeAssistant) -> None:
    """注册静态资源与侧边栏面板（重复调用安全）。"""
    if hass.data.get(_PANEL_REGISTERED):
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(WWW_DIR), False)]
    )
    try:
        from homeassistant.components.panel_custom import async_register_panel

        await async_register_panel(
            hass,
            frontend_url_path=f"/{PANEL_URL_PATH}",
            webcomponent_name="llm-balance-panel",
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            module_url=f"{STATIC_URL}/panel.js",
            require_admin=True,
        )
    except Exception:  # noqa: BLE001 - 面板注册失败不应影响集成本身
        _LOGGER.exception("注册侧边栏面板失败")
    hass.data[_PANEL_REGISTERED] = True


async def _collect(hass: HomeAssistant) -> list[dict[str, Any]]:
    """汇总所有账号的快照。"""
    store = _store(hass)
    items: list[dict[str, Any]] = []
    for coordinator in _coordinators(hass):
        snapshot = coordinator.data
        if snapshot is None:
            continue
        payload = snapshot.to_dict()
        account = await store.get_account(snapshot.account_id)
        payload["enabled"] = account.enabled if account else True
        payload["credential_mask"] = (
            account.to_public()["credential_mask"] if account else {}
        )
        items.append(payload)
    items.sort(key=lambda item: (item["platform"], item["mode"], item["account_id"]))
    return items


class LlmBalancePlatformsView(HomeAssistantView):
    url = f"/api/{DOMAIN}/platforms"
    name = f"api:{DOMAIN}:platforms"
    requires_auth = True

    @callback
    def get(self, request):
        return self.json({"items": platform_specs_payload()})


class LlmBalanceDashboardView(HomeAssistantView):
    url = f"/api/{DOMAIN}/dashboard"
    name = f"api:{DOMAIN}:dashboard"
    requires_auth = True

    async def get(self, request):
        hass = request.app[KEY_HASS]
        if request.query.get("refresh") == "1":
            for coordinator in _coordinators(hass):
                await coordinator.async_request_refresh()
        items = await _collect(hass)
        ok = sum(1 for item in items if item["status"] == "ok")
        last_update = max((item["fetched_at"] for item in items), default="")
        return self.json(
            {
                "items": items,
                "summary": {
                    "total": len(items),
                    "ok": ok,
                    "failed": len(items) - ok,
                    "last_update": last_update,
                },
            }
        )


class LlmBalanceAccountsView(HomeAssistantView):
    url = f"/api/{DOMAIN}/accounts"
    name = f"api:{DOMAIN}:accounts"
    requires_auth = True

    async def get(self, request):
        hass = request.app[KEY_HASS]
        accounts = await _store(hass).list_accounts()
        return self.json({"items": [account.to_public() for account in accounts]})

    async def post(self, request):
        hass = request.app[KEY_HASS]
        body = await request.json()
        platform = body.get("platform")
        mode = body.get("mode")
        label = str(body.get("label") or "").strip()
        credentials = body.get("credentials") or {}
        try:
            validate_target(platform, mode)
            validate_options(body.get("options") or {})
        except ValueError as exc:
            return self.json({"detail": str(exc)}, status_code=400)

        missing = missing_credentials(platform, mode, credentials)
        if missing:
            return self.json(
                {"detail": f"缺少必填凭据：{'、'.join(missing)}"}, status_code=400
            )
        if not label:
            return self.json({"detail": "请填写备注名称"}, status_code=400)

        account = await _store(hass).create_account(
            platform=platform,
            mode=mode,
            label=label,
            credentials=credentials,
            options=body.get("options") or {},
            enabled=bool(body.get("enabled", True)),
        )
        return self.json(account.to_public(), status_code=201)


class LlmBalanceAccountView(HomeAssistantView):
    url = f"/api/{DOMAIN}/accounts/{{account_id}}"
    name = f"api:{DOMAIN}:account"
    requires_auth = True

    async def put(self, request, account_id: str):
        hass = request.app[KEY_HASS]
        account_id = int(account_id)
        body = await request.json()
        store = _store(hass)
        account = await store.get_account(account_id)
        if account is None:
            return self.json({"detail": "账号不存在"}, status_code=404)

        target_mode = body.get("mode") or account.mode
        try:
            validate_target(account.platform, target_mode)
            validate_options(body.get("options") or {})
        except ValueError as exc:
            return self.json({"detail": str(exc)}, status_code=400)

        credentials = body.get("credentials")
        if credentials:
            merged = dict(account.credentials)
            merged.update({k: v for k, v in credentials.items() if v})
            missing = missing_credentials(account.platform, target_mode, merged)
            if missing:
                return self.json(
                    {"detail": f"缺少必填凭据：{'、'.join(missing)}"}, status_code=400
                )

        updated = await store.update_account(
            account_id,
            label=body.get("label"),
            mode=body.get("mode"),
            credentials=credentials,
            options=body.get("options"),
            enabled=body.get("enabled"),
        )
        return self.json(updated.to_public() if updated else {})

    async def delete(self, request, account_id: str):
        hass = request.app[KEY_HASS]
        account_id = int(account_id)
        if not await _store(hass).delete_account(account_id):
            return self.json({"detail": "账号不存在"}, status_code=404)
        return self.json({"deleted": account_id})


class LlmBalanceAccountRefreshView(HomeAssistantView):
    url = f"/api/{DOMAIN}/accounts/{{account_id}}/refresh"
    name = f"api:{DOMAIN}:account_refresh"
    requires_auth = True

    async def post(self, request, account_id: str):
        hass = request.app[KEY_HASS]
        account_id = int(account_id)
        for coordinator in _coordinators(hass):
            if coordinator.account and coordinator.account.id == account_id:
                snapshot = await coordinator.async_force_refresh()
                return self.json(snapshot.to_dict() if snapshot else {})
        return self.json({"detail": "账号不存在"}, status_code=404)


class LlmBalanceSettingsView(HomeAssistantView):
    url = f"/api/{DOMAIN}/settings"
    name = f"api:{DOMAIN}:settings"
    requires_auth = True

    async def get(self, request):
        hass = request.app[KEY_HASS]
        return self.json(await async_get_settings(hass))

    async def put(self, request):
        hass = request.app[KEY_HASS]
        body = await request.json()
        if "locale" in body and body["locale"] not in ("zh-CN", "en-US"):
            return self.json({"detail": "locale 仅支持 zh-CN 或 en-US"}, status_code=400)
        if "minimax_base_url" in body:
            url = str(body["minimax_base_url"]).strip()
            if not url.startswith("https://"):
                return self.json(
                    {"detail": "MiniMax 地址必须以 https:// 开头"}, status_code=400
                )
            body["minimax_base_url"] = url.rstrip("/")
        if "bill_month" in body:
            month = str(body["bill_month"]).strip()
            if month and (len(month) != 7 or month[4] != "-"):
                return self.json(
                    {"detail": "账期月份格式应为 YYYY-MM"}, status_code=400
                )
            body["bill_month"] = month
        return self.json(await async_save_settings(hass, body))


VIEWS = [
    LlmBalancePlatformsView,
    LlmBalanceDashboardView,
    LlmBalanceAccountsView,
    LlmBalanceAccountView,
    LlmBalanceAccountRefreshView,
    LlmBalanceSettingsView,
]


async def async_register_views(hass: HomeAssistant) -> None:
    """注册全部 HTTP 视图。"""
    for view in VIEWS:
        hass.http.register_view(view())
