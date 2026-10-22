from __future__ import annotations

from .aliyun import AliyunProvider
from ..models import PLATFORM_SPECS, PlatformSpec, platform_specs_payload
from .deepseek import DeepseekProvider
from .minimax import MinimaxProvider

_PROVIDERS = {
    "aliyun": AliyunProvider,
    "minimax": MinimaxProvider,
    "deepseek": DeepseekProvider,
}


def get_provider(platform: str):
    provider_cls = _PROVIDERS.get(platform)
    if provider_cls is None:
        raise ValueError(f"未知平台：{platform}")
    return provider_cls()


__all__ = [
    "AliyunProvider",
    "DeepseekProvider",
    "MinimaxProvider",
    "PLATFORM_SPECS",
    "PlatformSpec",
    "get_provider",
    "platform_specs_payload",
]
