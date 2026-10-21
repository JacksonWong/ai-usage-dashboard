from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .providers.base import PLATFORM_SPECS


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


ACCOUNT_OPTION_VALIDATORS: dict[str, Any] = {
    "dimension": lambda value: value in ("BASE_MODEL", "API_KEY_ID"),
    "bill_month": lambda value: not value
    or (isinstance(value, str) and len(value) == 7 and value[4] == "-" and value[:4].isdigit()),
    "locale": lambda value: value in ("zh-CN", "en-US"),
}


def validate_options(options: dict[str, Any]) -> None:
    for key, value in options.items():
        validator = ACCOUNT_OPTION_VALIDATORS.get(key)
        if validator is None:
            continue
        if not validator(value):
            raise ValueError(f"选项 {key} 取值不合法：{value}")


def validate_target(platform: str, mode: str) -> list[str]:
    """校验平台/模式组合，返回缺失的必填凭据字段名。"""
    spec = PLATFORM_SPECS.get(platform)
    if spec is None:
        raise ValueError(f"未知平台：{platform}")
    mode_spec = spec.mode(mode)
    if mode_spec is None:
        valid = "、".join(m.label for m in spec.modes)
        raise ValueError(f"{spec.label} 不支持该模式，可选：{valid}")
    return [f.name for f in mode_spec.fields if f.required]


def missing_credentials(platform: str, mode: str, credentials: dict[str, str]) -> list[str]:
    required = validate_target(platform, mode)
    return [
        name
        for name in required
        if not (credentials.get(name) or "").strip()
    ]
