"""与 Home Assistant 解耦的核心模型：账号、平台/凭据规格。

该模块不得引入 homeassistant 相关依赖，以便独立部署模式直接复用。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Account:
    """一个接入账号（平台 + 模式 + 凭据 + 选项）。"""

    id: int
    platform: str
    mode: str
    label: str
    credentials: dict[str, str] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""
    last_ok_at: str | None = None
    last_error: str | None = None

    def to_public(self) -> dict[str, Any]:
        from .crypto_mask import mask

        return {
            "id": self.id,
            "platform": self.platform,
            "mode": self.mode,
            "label": self.label,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_ok_at": self.last_ok_at,
            "last_error": self.last_error,
            "options": self.options,
            "credential_mask": {
                key: mask(value) for key, value in self.credentials.items() if value
            },
            "credential_keys": sorted(self.credentials.keys()),
        }


@dataclass(frozen=True)
class CredentialField:
    name: str
    label: str
    secret: bool = True
    required: bool = False
    placeholder: str = ""
    help: str = ""
    default: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModeSpec:
    key: str
    label: str
    description: str
    fields: tuple[CredentialField, ...]
    docs: tuple[str, ...]


@dataclass(frozen=True)
class PlatformSpec:
    key: str
    label: str
    short: str
    accent: str
    modes: tuple[ModeSpec, ...]
    docs: tuple[str, ...]

    def mode(self, mode_key: str) -> ModeSpec | None:
        return next((m for m in self.modes if m.key == mode_key), None)


_AK_FIELDS = (
    CredentialField(
        name="access_key_id",
        label="AccessKey ID",
        secret=False,
        required=True,
        placeholder="LTAI5txxxxxxxxxxxx",
        help="阿里云 AccessKey ID，Model Studio 与账务中心 OpenAPI 均用它签名。",
    ),
    CredentialField(
        name="access_key_secret",
        label="AccessKey Secret",
        secret=True,
        required=True,
        placeholder="••••••••••••",
        help="与 AccessKey ID 配套，用于 ACS3-HMAC-SHA256 签名。",
    ),
    CredentialField(
        name="security_token",
        label="STS SecurityToken（可选）",
        secret=True,
        required=False,
        placeholder="",
        help="使用 RAM 角色临时凭证时填写；长期 AK 留空。",
    ),
    CredentialField(
        name="region_id",
        label="地域 ID",
        secret=False,
        required=False,
        placeholder="cn-beijing",
        default="cn-beijing",
        help="百炼接入地域，默认 cn-beijing（华北 2 北京）。",
    ),
)

PLATFORM_SPECS: dict[str, PlatformSpec] = {
    "aliyun": PlatformSpec(
        key="aliyun",
        label="阿里云百炼",
        short="百炼",
        accent="aliyun",
        modes=(
            ModeSpec(
                key="payg",
                label="按量付费",
                description="账单概览 / 趋势 / API Key 分摊 + 阿里云账户可用额度。",
                fields=_AK_FIELDS,
                docs=(
                    "https://docs.bailian.console.aliyun.com/zh/model-studio/api-modelstudio-2026-02-10-getbillingoverview",
                    "https://docs.bailian.console.aliyun.com/zh/model-studio/api-modelstudio-2026-02-10-getbillingtrend",
                    "https://help.aliyun.com/zh/model-studio/get-api-key",
                ),
            ),
            ModeSpec(
                key="token_plan",
                label="订阅 Token Plan",
                description="席位额度统计 / 席位明细 / 共享包，计量单位为 Credits。",
                fields=_AK_FIELDS,
                docs=(
                    "https://help.aliyun.com/zh/model-studio/get-subscription-stats",
                    "https://help.aliyun.com/zh/model-studio/get-subscription-seat-details",
                    "https://help.aliyun.com/zh/model-studio/list-subscription-shared-packages",
                ),
            ),
        ),
        docs=("https://help.aliyun.com/zh/model-studio/token-plan-overview",),
    ),
    "minimax": PlatformSpec(
        key="minimax",
        label="MiniMax",
        short="MiniMax",
        accent="minimax",
        modes=(
            ModeSpec(
                key="token_plan",
                label="M Plan（订阅）",
                description="M Plan 剩余额度，受 5 小时窗口与周窗口约束。",
                fields=(
                    CredentialField(
                        name="api_key",
                        label="订阅 Key",
                        secret=True,
                        required=True,
                        placeholder="eyJhbGciOi...",
                        help="开放平台「订阅管理 > M Plan」获取的订阅 Key，非按量计费 API Key。",
                    ),
                ),
                docs=("https://platform.minimax.cn/docs/m-plan/faq",),
            ),
        ),
        docs=("https://platform.minimax.cn/docs/m-plan/faq",),
    ),
    "deepseek": PlatformSpec(
        key="deepseek",
        label="DeepSeek",
        short="DeepSeek",
        accent="deepseek",
        modes=(
            ModeSpec(
                key="payg",
                label="按量付费",
                description="账户余额（总余额 / 赠金 / 充值）。",
                fields=(
                    CredentialField(
                        name="api_key",
                        label="API Key",
                        secret=True,
                        required=True,
                        placeholder="sk-xxxxxxxxxxxx",
                        help="DeepSeek 开放平台 API Key。",
                    ),
                ),
                docs=("https://api-docs.deepseek.com/zh-cn/api/get-user-balance",),
            ),
        ),
        docs=("https://api-docs.deepseek.com/zh-cn/api/get-user-balance",),
    ),
}


def platform_specs_payload() -> list[dict[str, Any]]:
    return [
        {
            "key": spec.key,
            "label": spec.label,
            "short": spec.short,
            "accent": spec.accent,
            "docs": list(spec.docs),
            "modes": [
                {
                    "key": mode.key,
                    "label": mode.label,
                    "description": mode.description,
                    "docs": list(mode.docs),
                    "fields": [f.to_dict() for f in mode.fields],
                }
                for mode in spec.modes
            ],
        }
        for spec in PLATFORM_SPECS.values()
    ]


ACCOUNT_OPTION_VALIDATORS: dict[str, Any] = {
    "dimension": lambda value: value in ("BASE_MODEL", "API_KEY_ID"),
    "bill_month": lambda value: not value
    or (
        isinstance(value, str)
        and len(value) == 7
        and value[4] == "-"
        and value[:4].isdigit()
    ),
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
    """校验平台/模式组合，返回该模式下的必填凭据字段名。"""
    spec = PLATFORM_SPECS.get(platform)
    if spec is None:
        raise ValueError(f"未知平台：{platform}")
    mode_spec = spec.mode(mode)
    if mode_spec is None:
        valid = "、".join(m.label for m in spec.modes)
        raise ValueError(f"{spec.label} 不支持该模式，可选：{valid}")
    return [f.name for f in mode_spec.fields if f.required]


def missing_credentials(
    platform: str, mode: str, credentials: dict[str, str]
) -> list[str]:
    required = validate_target(platform, mode)
    return [name for name in required if not (credentials.get(name) or "").strip()]
