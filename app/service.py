from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .config import load_settings
from .db import Account, list_accounts, record_result
from .providers import get_provider
from .snapshot import Snapshot


class DashboardService:
    """抓取各账号快照并缓存，避免每次页面刷新都打爆官方接口。"""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._cache: dict[int, Snapshot] = {}
        self._lock = asyncio.Lock()

    async def client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = load_settings().get("request_timeout_seconds", 20)
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(float(timeout), connect=10.0),
                follow_redirects=False,
                headers={"User-Agent": "ai-usage-dashboard/0.1"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def refresh_account(self, account: Account) -> Snapshot:
        provider = get_provider(account.platform)
        client = await self.client()
        settings = load_settings()
        try:
            snapshot = await provider.fetch(client, account, settings)
        except Exception as exc:  # noqa: BLE001 - 任何异常都要转成可见的错误卡
            snapshot = Snapshot(
                account_id=account.id,
                platform=account.platform,
                mode=account.mode,
                label=account.label,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                fetched_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
        record_result(account.id, snapshot.status == "ok", snapshot.error)
        self._cache[account.id] = snapshot
        return snapshot

    async def snapshots(self, force: bool = False) -> list[Snapshot]:
        accounts = list_accounts()
        if not accounts:
            return []

        fresh_enough = datetime.now(timezone.utc) - timedelta(seconds=20)
        to_fetch: list[Account] = []
        results: list[Snapshot] = []
        for account in accounts:
            cached = self._cache.get(account.id)
            if not force and cached is not None and cached.fetched_at:
                try:
                    fetched = datetime.fromisoformat(cached.fetched_at)
                except ValueError:
                    fetched = fresh_enough
                if fetched > fresh_enough:
                    results.append(cached)
                    continue
            to_fetch.append(account)

        if to_fetch:
            async with self._lock:
                client = await self.client()
                settings = load_settings()
                fetched = await asyncio.gather(
                    *(self._fetch_one(account, client, settings) for account in to_fetch),
                    return_exceptions=True,
                )
            for account, outcome in zip(to_fetch, fetched):
                if isinstance(outcome, BaseException):
                    snapshot = Snapshot(
                        account_id=account.id,
                        platform=account.platform,
                        mode=account.mode,
                        label=account.label,
                        status="error",
                        error=f"{type(outcome).__name__}: {outcome}",
                    )
                else:
                    snapshot = outcome
                record_result(account.id, snapshot.status == "ok", snapshot.error)
                self._cache[account.id] = snapshot
                results.append(snapshot)

        order = {account.id: index for index, account in enumerate(accounts)}
        results.sort(key=lambda item: order.get(item.account_id, 0))
        return results

    async def _fetch_one(
        self, account: Account, client: httpx.AsyncClient, settings: dict[str, Any]
    ) -> Snapshot:
        provider = get_provider(account.platform)
        return await provider.fetch(client, account, settings)

    def cached(self, account_id: int) -> Snapshot | None:
        return self._cache.get(account_id)

    def invalidate(self, account_id: int | None = None) -> None:
        if account_id is None:
            self._cache.clear()
        else:
            self._cache.pop(account_id, None)


service = DashboardService()
