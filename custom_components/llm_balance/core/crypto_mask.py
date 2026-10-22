"""凭据掩码工具（与 Home Assistant 解耦）。"""

from __future__ import annotations


def mask(secret: str, keep: int = 4) -> str:
    if not secret:
        return ""
    if len(secret) <= keep * 2:
        return "*" * len(secret)
    return f"{secret[:keep]}{'*' * 6}{secret[-keep:]}"
