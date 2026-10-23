from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from ..models import Account
from ..format import format_money, now_iso, to_float
from ..http_client import ApiError, request_json
from ..snapshot import Metric, ModelItem, Snapshot
from .base import Provider

BALANCE_URL = "https://api.deepseek.com/user/balance"
MODELS_URL = "https://api.deepseek.com/models"


class DeepseekProvider(Provider):
    platform = "deepseek"

    async def fetch(
        self,
        client: httpx.AsyncClient,
        account: Account,
        settings: dict[str, Any],
    ) -> Snapshot:
        started = datetime.now()
        api_key = account.credentials.get("api_key", "").strip()
        if not api_key:
            return self._error(account, started, "未配置 API Key")

        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            payload = await request_json(
                client,
                "GET",
                BALANCE_URL,
                headers=headers,
            )
        except ApiError as exc:
            return self._error(account, started, str(exc))

        available = payload.get("is_available")
        if available is False:
            snapshot = self._error(account, started, "账户余额不可用（is_available = false）")
            snapshot.raw = payload
            return snapshot

        snapshot = Snapshot(
            account_id=account.id,
            platform=self.platform,
            mode=account.mode,
            label=account.label,
            fetched_at=now_iso(),
        )

        balances = payload.get("balance_infos")
        if not isinstance(balances, list) or not balances:
            snapshot = self._error(account, started, "响应中缺少 balance_infos")
            snapshot.raw = payload
            return snapshot

        for info in balances:
            if not isinstance(info, dict):
                continue
            currency = str(info.get("currency") or "CNY")
            total = to_float(info.get("total_balance"))
            granted = to_float(info.get("granted_balance"))
            topped_up = to_float(info.get("topped_up_balance"))
            if total is not None:
                snapshot.metrics.append(
                    Metric(
                        key="total_balance",
                        label=f"总余额（{currency}）",
                        value=total,
                        display=format_money(total, currency),
                        unit=currency,
                        level="ok" if total > 0 else "danger",
                        hint="赠金余额 + 充值余额",
                    )
                )
            if granted is not None:
                snapshot.metrics.append(
                    Metric(
                        key="granted_balance",
                        label="赠金余额",
                        value=granted,
                        display=format_money(granted, currency),
                        unit=currency,
                        hint="未过期的赠金余额",
                    )
                )
            if topped_up is not None:
                snapshot.metrics.append(
                    Metric(
                        key="topped_up_balance",
                        label="充值余额",
                        value=topped_up,
                        display=format_money(topped_up, currency),
                        unit=currency,
                    )
                )

        snapshot.raw = payload

        await self._fetch_models(client, snapshot, headers)

        snapshot.latency_ms = int((datetime.now() - started).total_seconds() * 1000)
        return snapshot

    async def _fetch_models(
        self,
        client: httpx.AsyncClient,
        snapshot: Snapshot,
        headers: dict[str, str],
    ) -> None:
        """拉取可用模型列表；失败只记 note，不影响余额快照。"""
        try:
            payload = await request_json(client, "GET", MODELS_URL, headers=headers)
        except ApiError as exc:
            snapshot.notes.append(f"模型列表获取失败：{exc}")
            return

        data = payload.get("data")
        if not isinstance(data, list):
            snapshot.notes.append("模型列表响应缺少 data 字段")
            return

        for entry in data:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            model_id = str(entry["id"])
            snapshot.models.append(
                ModelItem(
                    id=model_id,
                    name=str(entry.get("name") or model_id),
                    context_window=_to_int(entry.get("context_window")),
                    max_output_tokens=_to_int(entry.get("max_output_tokens")),
                    input_modalities=_to_str_list(entry.get("input_modalities")),
                    output_modalities=_to_str_list(entry.get("output_modalities")),
                )
            )

    def _error(self, account: Account, started: datetime, message: str) -> Snapshot:
        return Snapshot(
            account_id=account.id,
            platform=self.platform,
            mode=account.mode,
            label=account.label,
            status="error",
            error=message,
            fetched_at=now_iso(),
            latency_ms=int((datetime.now() - started).total_seconds() * 1000),
        )


def _to_int(value: object) -> int | None:
    number = to_float(value)
    return int(number) if number is not None else None


def _to_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]
