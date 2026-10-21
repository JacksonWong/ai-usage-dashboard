from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from ..db import Account
from ..format import format_money, now_iso, to_float
from ..http_client import ApiError, request_json
from ..snapshot import BreakdownItem, Metric, Snapshot
from .base import Provider

BALANCE_URL = "https://api.deepseek.com/user/balance"


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

        try:
            payload = await request_json(
                client,
                "GET",
                BALANCE_URL,
                headers={"Authorization": f"Bearer {api_key}"},
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
            if granted is not None or topped_up is not None:
                parts = []
                if granted is not None:
                    parts.append(("赠金", granted))
                if topped_up is not None:
                    parts.append(("充值", topped_up))
                combined = sum(value for _, value in parts)
                for name, value in parts:
                    snapshot.breakdown.append(
                        BreakdownItem(
                            name=name,
                            value=value,
                            display=format_money(value, currency),
                            percentage=(value / combined) if combined else None,
                            dimension="余额构成",
                        )
                    )

        snapshot.raw = payload
        snapshot.latency_ms = int((datetime.now() - started).total_seconds() * 1000)
        return snapshot

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
