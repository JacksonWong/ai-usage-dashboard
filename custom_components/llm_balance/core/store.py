"""账号存储抽象。

独立部署用 SQLite 实现，Home Assistant 用 config entry 实现，
两者实现同一组方法，上层无需区分。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .models import Account


@runtime_checkable
class AccountStore(Protocol):
    """账号增删改查的统一接口。"""

    async def list_accounts(self) -> list[Account]: ...

    async def get_account(self, account_id: int) -> Account | None: ...

    async def create_account(
        self,
        platform: str,
        mode: str,
        label: str,
        credentials: dict[str, str],
        options: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> Account: ...

    async def update_account(
        self,
        account_id: int,
        *,
        label: str | None = None,
        mode: str | None = None,
        credentials: dict[str, str] | None = None,
        options: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> Account | None: ...

    async def delete_account(self, account_id: int) -> bool: ...
