"""Provider 抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from ..models import Account
from ..snapshot import Snapshot


class Provider(ABC):
    platform: str

    @abstractmethod
    async def fetch(
        self,
        client: httpx.AsyncClient,
        account: Account,
        settings: dict[str, Any],
    ) -> Snapshot:
        raise NotImplementedError
