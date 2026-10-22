from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from custom_components.llm_balance.core.models import Account
from custom_components.llm_balance.core.service import refresh_account as _refresh
from custom_components.llm_balance.core.snapshot import Snapshot

from .config import load_settings
from .db import record_result
from .store import store


class DashboardService:
    """抓取各账号快照并缓存，避免每次页面刷新都打爆官方接口。"""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._cache: dict[int, Snapshot] = {}
        self._lock = asyncio.Lock()
        self.store = store

    def _build_client(self) -> httpx.AsyncClient:
        """构造 HTTP 客户端（会同步加载 CA 证书，需在线程中执行）。"""
        timeout = load_settings().get("request_timeout_seconds", 20)
        return httpx.AsyncClient(
            timeout=httpx.Timeout(float(timeout), connect=10.0),
            follow_redirects=False,
            headers={"User-Agent": "ai-usage-dashboard/0.1"},
        )

    async def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = await asyncio.to_thread(self._build_client)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def refresh_account(self, account: Account) -> Snapshot:
        client = await self.client()
        snapshot = await _refresh(client, account, load_settings())
        record_result(account.id, snapshot.status == "ok", snapshot.error)
        self._cache[account.id] = snapshot
        return snapshot

    async def snapshots(self, force: bool = False) -> list[Snapshot]:
        accounts = await self.store.list_accounts()
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
                    *(_refresh(client, account, settings) for account in to_fetch),
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

    def cached(self, account_id: int) -> Snapshot | None:
        return self._cache.get(account_id)

    def invalidate(self, account_id: int | None = None) -> None:
        if account_id is None:
            self._cache.clear()
        else:
            self._cache.pop(account_id, None)


service = DashboardService()
