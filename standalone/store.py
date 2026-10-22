"""独立部署的账号存储：SQLite 实现，套一层异步接口。"""

from __future__ import annotations

from typing import Any

from custom_components.llm_balance.core.models import Account

from . import db


class SqliteAccountStore:
    """把同步的 SQLite 读写包装成统一的异步账号存储接口。"""

    async def list_accounts(self) -> list[Account]:
        return db.list_accounts()

    async def get_account(self, account_id: int) -> Account | None:
        return db.get_account(account_id)

    async def create_account(
        self,
        platform: str,
        mode: str,
        label: str,
        credentials: dict[str, str],
        options: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> Account:
        return db.create_account(
            platform=platform,
            mode=mode,
            label=label,
            credentials=credentials,
            options=options,
            enabled=enabled,
        )

    async def update_account(
        self,
        account_id: int,
        *,
        label: str | None = None,
        mode: str | None = None,
        credentials: dict[str, str] | None = None,
        options: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> Account | None:
        return db.update_account(
            account_id,
            label=label,
            mode=mode,
            credentials=credentials,
            options=options,
            enabled=enabled,
        )

    async def delete_account(self, account_id: int) -> bool:
        return db.delete_account(account_id)


store = SqliteAccountStore()
