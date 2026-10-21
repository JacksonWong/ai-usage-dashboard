from __future__ import annotations

import asyncio
from typing import Any

from .config import load_settings
from .service import service


class RefreshScheduler:
    """按全局设置里的间隔在后台周期性刷新所有账号。"""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            interval = int(load_settings().get("auto_refresh_seconds", 300) or 0)
            if interval <= 0:
                await asyncio.sleep(5)
                continue
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                pass
            try:
                await service.snapshots(force=True)
            except Exception:  # noqa: BLE001 - 后台任务不允许因单次失败退出
                continue


scheduler = RefreshScheduler()
