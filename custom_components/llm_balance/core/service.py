"""共享的抓取逻辑：独立部署与 Home Assistant 集成共用。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

from .models import Account
from .providers import get_provider
from .snapshot import Snapshot


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def refresh_account(
    client: httpx.AsyncClient,
    account: Account,
    settings: dict[str, Any] | None = None,
) -> Snapshot:
    """抓取单个账号的快照，任何异常都转成可见的错误态。"""
    provider = get_provider(account.platform)
    try:
        return await provider.fetch(client, account, settings or {})
    except Exception as exc:  # noqa: BLE001 - 任何异常都要落到卡片上
        return Snapshot(
            account_id=account.id,
            platform=account.platform,
            mode=account.mode,
            label=account.label,
            status="error",
            error=f"{type(exc).__name__}: {exc}",
            fetched_at=now_iso(),
        )


async def refresh_all(
    client: httpx.AsyncClient,
    accounts: Iterable[Account],
    settings: dict[str, Any] | None = None,
) -> list[Snapshot]:
    """并发抓取所有账号，保持传入顺序。"""
    account_list = list(accounts)
    if not account_list:
        return []
    return list(
        await asyncio.gather(
            *(refresh_account(client, account, settings) for account in account_list)
        )
    )
