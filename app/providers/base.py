from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from ..db import Account
from ..snapshot import Snapshot


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
