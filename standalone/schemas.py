"""独立部署模式的 HTTP 出入参模型（pydantic）。

Home Assistant 集成使用 voluptuous 配置流，不依赖本模块。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AccountCreate(BaseModel):
    platform: str
    mode: str
    label: str = Field(min_length=1, max_length=64)
    credentials: dict[str, str] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class AccountUpdate(BaseModel):
    mode: str | None = None
    label: str | None = Field(default=None, min_length=1, max_length=64)
    credentials: dict[str, str] | None = None
    options: dict[str, Any] | None = None
    enabled: bool | None = None


class SettingsUpdate(BaseModel):
    auto_refresh_seconds: int | None = Field(default=None, ge=0, le=86400)
    bill_month: str | None = None
    locale: str | None = None
    minimax_base_url: str | None = None
    request_timeout_seconds: int | None = Field(default=None, ge=5, le=120)
